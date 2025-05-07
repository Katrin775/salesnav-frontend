# main.py – Komplettes FastAPI-Backend mit Upload, Rollenfilter und Enrichment
# Angepasst für Python 3.13 Kompatibilität

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import uuid
import csv
import time
import random
import codecs
import chardet
import os
import sys
import subprocess
from urllib.parse import urljoin

# Versuche, Selenium statt Playwright zu verwenden
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    print("✅ Selenium importiert")
    USE_SELENIUM = True
except ImportError:
    print("⚠️ Selenium nicht gefunden, versuche Playwright...")
    try:
        from playwright.sync_api import sync_playwright
        print("✅ Playwright importiert")
        USE_SELENIUM = False
    except (ImportError, NotImplementedError) as e:
        print(f"❌ Fehler beim Import: {e}")
        raise ImportError("Weder Selenium noch Playwright konnten importiert werden. Bitte eines davon installieren.")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
RESULT_DIR = Path("results")
PROFILE_DIR = Path("profile").resolve()
UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

MAX_KONTAKTE_PRO_FIRMA = 3
WARTEN_ZWISCHEN_FIRMEN = (5, 8)
DEFAULT_FIELDS = ["Firma 1", "Firma (Gesamt)", "Name", "Aussteller", "Unternehmen"]

# Konstanten für die Pausensteuerung
PAUSE_INTERVAL_MIN = 25  # Minuten
PAUSE_INTERVAL_MAX = 40  # Minuten
PAUSE_DURATION_MIN = 4   # Minuten
PAUSE_DURATION_MAX = 8   # Minuten
RELOGIN_AFTER_PAUSES = 2  # Nach wievielen Pausen soll neu eingeloggt werden

POSITIONEN = {
    "Marketing": ["marketing", "brand", "performance", "digitale projekte", "e-commerce"],
    "IT": ["it", "cio", "edv", "admin", "entwicklung", "digital", "projekt", "sap"],
    "HR": ["personal", "recruiting", "employer", "bgm", "büroleitung"],
    "GF": ["geschäftsleitung", "leitung", "ceo", "coo", "cfo", "betriebsleitung", "prokurist", "geschäftsführer", "geschäftsführung", "founder", "gründer", "inhaber"],
    "Produktion": ["produktion", "lager", "logistik", "material", "konfektionierung"]
}

# Angepasste Stichwortliste für die Rollensuche
ALLE_ROLLEN_STICHWORTE = {
    "HR": ["HR", "Personal", "Personalleitung", "BGM", "Büroleitung", "Recruiting", "Buchhaltung", "Personal Entwicklung"],
    "Marketing": ["Marketing", "Marketingleitung", "Performance Marketing", "Online Marketing", "Brand Management", "Digitale Projekte", "E-Commerce", "Personalmarketing", "Employer Branding"],
    "IT": ["IT", "IT-Leitung", "IT-Innovation", "IT-Prozess", "Datenschutz", "IT-Admin", "Controlling", "EDV", "IT-Sicherheit", "Projektleitung", "SAP", "CIO"],
    "GF": ["Geschäftsleitung", "Geschäftsführer", "Geschäftsführung", "CEO", "COO", "CFO", "Founder", "Gründer", "Inhaber", "Prokurist", "Assistenz der Geschäftsleitung"],
    "Produktion": ["Produktion", "Fertigung", "Lager", "Materialwirtschaft", "Qualität", "Fuhrpark", "Konfektionierung", "Versand", "Digital Transformation", "Logistik"]
}

def detect_encoding(file_path):
    """Erkennt die Kodierung einer Datei"""
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
        if result['confidence'] > 0.7:
            return result['encoding']
    return 'utf-8-sig'  # Fallback auf UTF-8 mit BOM

def detect_delimiter(file_path, encoding):
    """Erkennt das Trennzeichen in einer CSV-Datei"""
    delimiters = [',', ';', '\t', '|']
    best_delimiter = ','  # Standard-Fallback
    most_columns = 0
    
    try:
        with codecs.open(file_path, 'r', encoding=encoding, errors='replace') as f:
            first_line = f.readline().strip()
            if not first_line:
                return best_delimiter
                
            for delimiter in delimiters:
                columns = len(first_line.split(delimiter))
                print(f"Delimiter '{delimiter}': {columns} Spalten in der ersten Zeile")
                if columns > most_columns:
                    most_columns = columns
                    best_delimiter = delimiter
    except Exception as e:
        print(f"⚠️ Fehler bei der Delimiter-Erkennung: {e}")
    
    return best_delimiter

def detect_firmenspalte(headers):
    """Findet die am besten passende Spalte für Firmennamen"""
    if not headers:
        return None
        
    for feld in DEFAULT_FIELDS:
        if feld in headers:
            return feld
            
    for header in headers:
        if header and any(kw in header.lower() for kw in ["firma", "company", "aussteller", "unternehmen"]):
            return header
            
    # Fallback auf erste oder zweite Spalte
    if len(headers) > 1:
        return headers[1]  # Zweite Spalte als Fallback
    elif headers:
        return headers[0]  # Erste Spalte als letzte Option
        
    return None

def load_csv(file_path):
    """Robustes CSV-Laden mit Fehlerbehandlung"""
    encoding = detect_encoding(file_path)
    delimiter = detect_delimiter(file_path, encoding)
    print(f"📊 Erkannte Kodierung: {encoding}, Trennzeichen: '{delimiter}'")
    
    headers = []
    rows = []
    
    try:
        with codecs.open(file_path, 'r', encoding=encoding, errors='replace') as f:
            # Prüfe, ob die Datei leer ist
            content = f.read()
            if not content.strip():
                raise ValueError("Die CSV-Datei ist leer")
            
            lines = content.splitlines()
            if not lines:
                raise ValueError("Keine Zeilen in der CSV-Datei gefunden")
                
            # Extrahiere Header
            header_line = lines[0]
            headers = [h.strip() for h in header_line.split(delimiter)]
            headers = [h for h in headers if h]  # Leere Headers entfernen
            
            if not headers:
                raise ValueError("Keine gültigen Header gefunden")
                
            # Verarbeite Datenzeilen
            for i in range(1, len(lines)):
                line = lines[i].strip()
                if not line:
                    continue
                    
                values = line.split(delimiter)
                
                # Anpassen der Zeilenlänge wenn nötig
                if len(values) < len(headers):
                    values.extend([''] * (len(headers) - len(values)))
                elif len(values) > len(headers):
                    values = values[:len(headers)]
                    
                row = {headers[j]: values[j].strip() for j in range(len(headers))}
                rows.append(row)
    except Exception as e:
        print(f"❌ Fehler beim CSV-Laden: {e}")
        raise ValueError(f"Fehler beim Verarbeiten der CSV-Datei: {e}")
    
    return headers, rows, delimiter

def start_browser():
    """Startet einen Browser mit Playwright"""
    print("🌐 Starte Browser mit Playwright...")
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
        page = browser.new_page()
        return page, p, browser  # Rückgabe: page, p, browser
    except Exception as e:
        print(f"❌ Fehler beim Starten von Playwright: {e}")
        
        # Nur wenn Selenium importiert wurde, versuche den Fallback
        if 'webdriver' in globals() and 'Options' in globals():
            print("⚠️ Fallback auf Selenium...")
            options = webdriver.ChromeOptions()
            options.add_argument(f"user-data-dir={str(PROFILE_DIR)}")
            driver = webdriver.Chrome(options=options)
            return driver, None, None
        else:
            raise ValueError(f"Weder Playwright noch Selenium konnte gestartet werden: {e}")

def perform_login(browser):
    """Führt den Login-Prozess durch"""
    if hasattr(browser, 'current_url'):  # Selenium-Browser
        browser.get("https://www.linkedin.com/sales/")
        time.sleep(3)
        if "login" in browser.current_url or "checkpoint" in browser.current_url:
            print("🔐 Bitte manuell einloggen...")
            input("Drücke ENTER nach dem Login...")
            time.sleep(2)
            if "login" in browser.current_url or "checkpoint" in browser.current_url:
                return False
            return True
        else:
            print("✅ Bereits eingeloggt")
            return True
    else:  # Playwright-Browser
        browser.goto("https://www.linkedin.com/sales/")
        time.sleep(3)
        if "login" in browser.url or "checkpoint" in browser.url:
            print("🔐 Bitte manuell einloggen...")
            input("Drücke ENTER nach dem Login...")
            time.sleep(2)
            if "login" in browser.url or "checkpoint" in browser.url:
                return False
            return True
        else:
            print("✅ Bereits eingeloggt")
            return True

def scrape_leads_selenium(driver, firma, relevante_keywords, rollen_filter):
    """Scrape-Funktion für Selenium"""
    contacts = []
    
    # Extrahiere Suchbegriffe für alle ausgewählten Rollen
    suchbegriffe = []
    for rolle in rollen_filter:
        if rolle in ALLE_ROLLEN_STICHWORTE:
            suchbegriffe.extend(ALLE_ROLLEN_STICHWORTE[rolle])
        else:
            suchbegriffe.append(rolle)
    
    # Kombiniere mit OR
    suchtext = " OR ".join(suchbegriffe)
    suche = f'"{firma}" AND ({suchtext})'
    
    print(f"🔍 Suche: {suche}")
    
    try:
        # Zur Suchseite navigieren
        driver.get("https://www.linkedin.com/sales/search/people")
        time.sleep(random.uniform(3.0, 5.0))
        
        # Suchfeld finden und Suchanfrage eingeben
        try:
            suchfeld = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Keywords für Suche']"))
            )
            suchfeld.clear()
            time.sleep(random.uniform(0.5, 0.8))
            
            # Zeichen für Zeichen eingeben für natürlicheres Verhalten
            for char in suche:
                suchfeld.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
                
            suchfeld.send_keys(Keys.ENTER)
            time.sleep(random.uniform(3.0, 5.0))
        except Exception as e:
            print(f"⚠️ Fehler bei der Suche: {e}")
            return []
        
        # Karten finden und verarbeiten
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, "li.artdeco-list__item")
            print(f"\nFirma: {firma} → Karten gefunden: {len(cards)}")
            
            seen_names = set()
            for card in cards[:MAX_KONTAKTE_PRO_FIRMA]:
                try:
                    card_text = card.text.strip()
                    print(f"RAW CARD TEXT:\n{card_text}\n---")
                    
                    lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                    if len(lines) < 3:
                        continue
                        
                    name, position, firmaline = lines[0], lines[1], lines[2]
                    if name in seen_names:
                        continue
                    seen_names.add(name)
                    
                    # Link finden
                    link_elements = card.find_elements(By.CSS_SELECTOR, "a[href*='/sales/lead/']")
                    link = ""
                    for l in link_elements:
                        href = l.get_attribute("href")
                        if href and "/sales/lead/" in href:
                            link = href
                            break
                            
                    if not link:
                        continue
                        
                    print(f"✔ Kontakt gefunden: {name} | {position}")
                    contacts.append({
                        "Name": name,
                        "Position": position,
                        "LinkedIn Profil": link
                    })
                except Exception as e:
                    print(f"❌ Fehler bei Card: {e}")
            
        except Exception as e:
            print(f"❌ Fehler beim Scrapen: {e}")
    
    except Exception as e:
        print(f"❌ Unerwarteter Fehler: {e}")
    
    return contacts

def scrape_leads_playwright(page, firma, relevante_keywords, rollen_filter):
    """Scrape-Funktion für Playwright"""
    # Extrahiere Suchbegriffe für alle ausgewählten Rollen
    suchbegriffe = []
    for rolle in rollen_filter:
        if rolle in ALLE_ROLLEN_STICHWORTE:
            suchbegriffe.extend(ALLE_ROLLEN_STICHWORTE[rolle])
        else:
            suchbegriffe.append(rolle)
    
    # Kombiniere mit OR
    suchtext = " OR ".join(suchbegriffe)
    suche = f'"{firma}" AND ({suchtext})'
    
    print(f"🔍 Suche: {suche}")
    
    page.goto("https://www.linkedin.com/sales/search/people")
    time.sleep(random.uniform(3.0, 5.0))

    try:
        suchfeld = page.locator("input[placeholder='Keywords für Suche']").first
        suchfeld.wait_for(state="visible", timeout=5000)
        suchfeld.focus()
        time.sleep(random.uniform(0.5, 0.8))
        suchfeld.fill("")
        for char in suche:
            suchfeld.type(char)
            time.sleep(random.uniform(0.05, 0.15))
        page.keyboard.press("Enter")
        time.sleep(random.uniform(3.0, 5.0))
    except Exception as e:
        print(f"⚠️ Fehler bei Suche nach '{firma}': {e}")
        return []

    contacts = []
    seen_names = set()
    cards = page.locator("li.artdeco-list__item").all()
    print(f"\nFirma: {firma} → Karten gefunden: {len(cards)}")

    for card in cards[:MAX_KONTAKTE_PRO_FIRMA]:
        try:
            card_text = card.inner_text().strip()
            print(f"RAW CARD TEXT:\n{card_text}\n---")
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]
            if len(lines) < 3:
                continue
            name, position, firmaline = lines[0], lines[1], lines[2]
            if name in seen_names:
                continue
            seen_names.add(name)

            link_els = card.locator("a[href*='/sales/lead/']").all()
            link = ""
            for l in link_els:
                href = l.get_attribute("href")
                if href and "/sales/lead/" in href:
                    link = urljoin("https://www.linkedin.com", href)
                    break
            if not link:
                continue

            print(f"✔ Kontakt gefunden: {name} | {position}")

            contacts.append({
                "Name": name,
                "Position": position,
                "LinkedIn Profil": link
            })
        except Exception as e:
            print(f"❌ Fehler bei Card: {e}")
            continue

    return contacts

def scrape_leads(browser, firma, relevante_keywords, rollen_filter):
    """Unified scrape function that works with both Selenium and Playwright"""
    if hasattr(browser, 'current_url'):  # Selenium-Browser
        return scrape_leads_selenium(browser, firma, relevante_keywords, rollen_filter)
    else:  # Playwright-Browser
        return scrape_leads_playwright(browser, firma, relevante_keywords, rollen_filter)

def run_enrichment(input_file: str, rollen: list[str]) -> Path:
    """Hauptfunktion für die Anreicherung der Daten"""
    try:
        # CSV-Daten laden
        headers, rows, delimiter = load_csv(input_file)
        
        # Relevante Keywords für die Rollen finden
        relevante_keywords = []
        for rolle in rollen:
            rolle = rolle.strip()
            if rolle in POSITIONEN:
                relevante_keywords.extend(POSITIONEN[rolle])

        # Firmenspalte finden
        firma_field = detect_firmenspalte(headers)
        if not firma_field:
            raise ValueError("Keine gültige Spalte für Firmennamen gefunden.")

        # Ausgabedatei vorbereiten
        basename = Path(input_file).stem
        output_file = RESULT_DIR / f"{basename}_result.csv"

        # Header für LinkedIn-Kontakte hinzufügen
        for i in range(1, MAX_KONTAKTE_PRO_FIRMA + 1):
            for feld in ["Name", "Position", "LinkedIn Profil"]:
                new_field = f"{feld} {i}"
                if new_field not in headers:
                    headers.append(new_field)

        # Browser starten
        browser, p, browser_context = start_browser()
        
        # Wenn der Browser nicht gestartet werden konnte, abbrechen
        if not browser:
            raise ValueError("Browser konnte nicht gestartet werden")
            
        # Login durchführen
        logged_in = perform_login(browser)
        if not logged_in:
            if p and browser_context:
                browser_context.close()
                p.stop()
            else:
                browser.quit()
            raise ValueError("LinkedIn-Login fehlgeschlagen")

        # CSV-Datei für Ergebnisse erstellen
        with open(output_file, "w", newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=headers, delimiter=delimiter or ',')
            writer.writeheader()

            # Pausensteuerung initialisieren
            next_pause_time = datetime.now() + timedelta(minutes=random.randint(PAUSE_INTERVAL_MIN, PAUSE_INTERVAL_MAX))
            pause_count = 0
            processed_count = 0

            # Verarbeite jede Firma
            for row in rows:
                current_time = datetime.now()
                
                # Prüfen, ob eine Pause fällig ist
                if current_time >= next_pause_time:
                    pause_duration = random.randint(PAUSE_DURATION_MIN, PAUSE_DURATION_MAX)
                    print(f"\n⏸️ Zeit für eine Pause! Pausiere für {pause_duration} Minuten...")
                    time.sleep(pause_duration * 60)  # Umrechnung in Sekunden
                    pause_count += 1
                    print(f"▶️ Pause beendet. Fortfahren mit der Suche... (Pausen bisher: {pause_count})")
                    
                    # Nach festgelegter Anzahl an Pausen neu einloggen
                    if pause_count % RELOGIN_AFTER_PAUSES == 0:
                        print("🔄 Führe Re-Login durch...")
                        if not perform_login(browser):
                            print("⚠️ Re-Login fehlgeschlagen! Versuche fortzufahren...")
                    
                    # Neuen Zeitpunkt für die nächste Pause festlegen
                    next_pause_time = datetime.now() + timedelta(minutes=random.randint(PAUSE_INTERVAL_MIN, PAUSE_INTERVAL_MAX))
                    print(f"⏱️ Nächste Pause geplant um: {next_pause_time.strftime('%H:%M:%S')}")

                firma = row.get(firma_field, "").strip()
                if not firma:
                    writer.writerow(row)
                    continue

                processed_count += 1
                print(f"\n🔍 Verarbeite Firma {processed_count}/{len(rows)}: {firma}")
                
                try:
                    contacts = scrape_leads(browser, firma, relevante_keywords, rollen)
                    if not contacts:
                        writer.writerow(row)
                    else:
                        for idx, contact in enumerate(contacts[:MAX_KONTAKTE_PRO_FIRMA]):
                            row_copy = row.copy()
                            for k, v in contact.items():
                                row_copy[f"{k} {idx+1}"] = v
                            writer.writerow(row_copy)
                            outfile.flush()
                    time.sleep(random.uniform(*WARTEN_ZWISCHEN_FIRMEN))
                except Exception as e:
                    print(f"❌ Unerwarteter Fehler bei '{firma}': {e}")
                    writer.writerow(row)
                    continue

        # Browser schließen
        if p and browser_context:
            browser_context.close()
            p.stop()
        else:
            browser.quit()
            
        print(f"\n✅ Verarbeitung abgeschlossen! Ergebnis gespeichert unter: {output_file}")
        return output_file
        
    except Exception as e:
        # Fehlerbehandlung für die gesamte Funktion
        print(f"❌ Fehler in run_enrichment: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.post("/upload")
def upload_csv(file: UploadFile = File(...), rollen: str = Form("")):
    """FastAPI-Endpunkt zum Hochladen einer CSV-Datei"""
    uid = uuid.uuid4().hex[:8]
    save_path = UPLOAD_DIR / f"{uid}_{file.filename}"
    
    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    rollen_liste = [r.strip() for r in rollen.split(",") if r.strip()]
    try:
        print(f"📤 Starte Enrichment für {file.filename} mit Rollen: {rollen_liste}")
        result_path = run_enrichment(str(save_path), rollen_liste)
        return {"result_file": result_path.name}
    except Exception as e:
        import traceback
        print(f"❌ Fehler beim Enrichment: {e}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/result/{filename}")
def download_result(filename: str):
    """FastAPI-Endpunkt zum Herunterladen des Ergebnisses"""
    file_path = RESULT_DIR / filename
    if file_path.exists():
        return FileResponse(file_path, filename=filename)
    return JSONResponse(status_code=404, content={"error": "Datei nicht gefunden."})

@app.get("/roles")
def get_roles():
    """FastAPI-Endpunkt zum Abrufen der verfügbaren Rollen"""
    return {
        "roles": [
            "Marketing",
            "Vertrieb",
            "HR",
            "IT",
            "Geschäftsführung",
            "Einkauf",
            "Logistik",
            "Produktmanagement"
        ]
    }