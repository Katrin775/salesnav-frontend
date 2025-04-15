from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil
import uuid
import csv
import time
import random
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

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

POSITIONEN = {
    "Marketing": ["Marketingleitung", "Leitung Performance Marketing", "Leitung Online Marketing", "Leitung Brand Management", "Leitung Digitale Projekte", "E-Commerce Leitung", "Personalmarketingleitung", "Leitung Employer Branding"],
    "IT": ["IT-Leitung", "Leitung IT-Innovation", "IT-Prozessleitung", "Datenschutzbeauftragter", "IT-Admin", "Leitung Controlling", "EDV-Leitung", "Leitung IT-Sicherheit", "IT Projektleitung", "SAP-Leitung", "Chief Information Officer (CIO)"],
    "HR": ["Personalleitung", "Leitung Personal Entwicklung", "BGM - Leitung", "Büroleitung", "Leitung Recruiting", "Leitung Buchhaltung"],
    "GF": ["Geschäftsleitung", "Technische Geschäftsleitung", "Kaufmännische Geschäftsleitung", "Prokurist", "Assistenz der Geschäftsleitung", "COO (Chief Operating Officer)", "Geschäftsleitung (Stellvertretung)"],
    "Produktion": ["Fertigungsleitung", "Lagerleitung", "Leitung Materialwirtschaft", "Leitung Produktion", "Leitung Produktion (Stellvertretung)", "Qualitätsleiter", "Leitung Fuhrpark", "Leitung Konfektionierung", "Leitung Versand", "Leitung Digital Transformation"]
}

def detect_firmenspalte(headers):
    for feld in DEFAULT_FIELDS:
        if feld in headers:
            return feld
    for header in headers:
        if any(kw in header.lower() for kw in ["firma", "company", "aussteller", "unternehmen"]):
            return header
    return None

def position_relevant(pos_text, relevante_keywords):
    if not relevante_keywords:
        return True
    text = pos_text.lower()
    return any(kw in text for kw in relevante_keywords)

def scrape_leads(page, firma, relevante_keywords):
    suche = f'"{firma}" AND (HR OR Personal OR Marketing OR IT OR Geschäftsleitung OR Einkauf OR Finanzen OR Produktion)'
    page.goto("https://www.linkedin.com/sales/search/people")
    time.sleep(random.uniform(3.0, 5.0))

    try:
        suchfeld = page.locator("input[placeholder='Keywords für Suche']").first
        suchfeld.wait_for(state="visible", timeout=5000)
        suchfeld.fill("")
        for char in suche:
            suchfeld.type(char)
            time.sleep(random.uniform(0.05, 0.15))
        page.keyboard.press("Enter")
        time.sleep(random.uniform(4.0, 6.0))
    except:
        return []

    contacts = []
    scroll_count = 0
    seen_names = set()
    while scroll_count < 10 and len(contacts) < MAX_KONTAKTE_PRO_FIRMA:
        cards = page.locator("li.artdeco-list__item").all()
        for card in cards:
            try:
                card_text = card.inner_text().strip()
                lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                if len(lines) < 3:
                    continue
                name, position, firmaline = lines[0], lines[1], lines[2]
                if name in seen_names:
                    continue
                seen_names.add(name)

                if not position_relevant(position, relevante_keywords):
                    continue

                link_els = card.locator("a[href*='/sales/lead/']").all()
                link = ""
                for l in link_els:
                    href = l.get_attribute("href")
                    if href and "/sales/lead/" in href:
                        link = urljoin("https://www.linkedin.com", href)
                        break
                if not link:
                    continue

                contacts.append({
                    "Name": name,
                    "Position": position,
                    "LinkedIn Profil": link
                })
                if len(contacts) >= MAX_KONTAKTE_PRO_FIRMA:
                    break
            except:
                continue
        page.mouse.wheel(0, 1000)
        time.sleep(random.uniform(2.0, 3.0))
        scroll_count += 1
    return contacts

def start_browser():
    p = sync_playwright().start()
    browser = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
    page = browser.new_page()
    return p, browser, page

def run_enrichment(input_file: str, rollen: list[str]) -> Path:
    relevante_keywords = []
    for rolle in rollen:
        rolle = rolle.strip()
        if rolle in POSITIONEN:
            relevante_keywords.extend(POSITIONEN[rolle])

    with open(input_file, newline='', encoding='utf-8-sig') as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)
        headers = reader.fieldnames.copy()

    firma_field = detect_firmenspalte(headers)
    if not firma_field:
        raise ValueError("Keine gültige Spalte für Firmennamen gefunden.")

    basename = Path(input_file).stem
    output_file = RESULT_DIR / f"{basename}_result.csv"

    for i in range(1, MAX_KONTAKTE_PRO_FIRMA + 1):
        for feld in ["Name", "Position", "LinkedIn Profil"]:
            new_field = f"{feld} {i}"
            if new_field not in headers:
                headers.append(new_field)

    p, browser, page = start_browser()
    page.goto("https://www.linkedin.com/sales/")
    time.sleep(3)
    if "login" in page.url or "checkpoint" in page.url:
        input("🔐 Bitte manuell einloggen und ENTER drücken...")

    with open(output_file, "w", newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=headers)
        writer.writeheader()

        for row in rows:
            firma = row.get(firma_field, "").strip()
            if not firma:
                writer.writerow(row)
                continue

            contacts = scrape_leads(page, firma, relevante_keywords)
            for idx, contact in enumerate(contacts[:MAX_KONTAKTE_PRO_FIRMA]):
                for k, v in contact.items():
                    row[f"{k} {idx+1}"] = v
            writer.writerow(row)
            time.sleep(random.uniform(*WARTEN_ZWISCHEN_FIRMEN))

    browser.close()
    p.stop()
    return output_file

@app.post("/upload")
async def upload_csv(file: UploadFile = File(...), rollen: str = Form("")):
    uid = uuid.uuid4().hex[:8]
    save_path = UPLOAD_DIR / f"{uid}_{file.filename}"
    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    rollen_liste = [r.strip() for r in rollen.split(",") if r.strip()]
    try:
        result_path = run_enrichment(str(save_path), rollen_liste)
        return {"result_file": result_path.name}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Fehler bei der Enrichment-Verarbeitung: {str(e)}"})

@app.get("/result/{filename}")
def download_result(filename: str):
    file_path = RESULT_DIR / filename
    if file_path.exists():
        return FileResponse(file_path, filename=filename)
    return JSONResponse(status_code=404, content={"error": "Datei nicht gefunden."})
