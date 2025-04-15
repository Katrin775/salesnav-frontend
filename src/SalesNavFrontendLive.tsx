import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";

const API_URL = "https://salesnav-enrich.onrender.com";

const positionOptions = [
  "Marketing",
  "IT",
  "HR",
  "GF",
  "Produktion"
];

export default function SalesNavFrontendLive() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rollen, setRollen] = useState<string[]>([]);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(10);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("rollen", rollen.join(","));

    try {
      const res = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error("Upload fehlgeschlagen");

      const data = await res.json();
      const resultFile = data.result_file;
      setProgress(100);
      setResultUrl(`${API_URL}/result/${resultFile}`);
    } catch (err) {
      setError("Fehler beim Upload. Bitte erneut versuchen.");
    } finally {
      setUploading(false);
    }
  };

  const handleRollenChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setRollen((prev) => {
      if (prev.includes(value)) {
        return prev.filter((r) => r !== value);
      } else {
        return [...prev, value];
      }
    });
  };

  return (
    <div className="min-h-screen bg-white text-black p-6">
      <div className="max-w-xl mx-auto">
        <div className="flex justify-center mb-6">
          <img
            src="https://www.kundenbeispiele.de/wp-content/uploads/2023/11/Design-ohne-Titel-2023-11-02T085025.735-e1723466180213.png"
            alt="Logo"
            className="h-24"
          />
        </div>

        <Card className="shadow-xl rounded-2xl border-black">
          <CardContent className="space-y-4 p-6">
            <h1 className="text-2xl font-bold">Sales Navigator Scraper</h1>
            <div className="space-y-2">
              <Label htmlFor="csv" className="block font-medium">CSV-Datei hochladen</Label>
              <Input
                id="csv"
                type="file"
                accept=".csv"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="border border-gray-300 p-2 rounded"
              />
            </div>

            <div className="space-y-2">
              <Label>Wählen Sie Positionen aus</Label>
              {positionOptions.map((position) => (
                <div key={position} className="flex items-center">
                  <input
                    type="checkbox"
                    value={position}
                    onChange={handleRollenChange}
                    checked={rollen.includes(position)}
                    className="mr-2"
                  />
                  <span>{position}</span>
                </div>
              ))}
            </div>

            <Button
              disabled={!file || uploading}
              className="bg-[#A4DED0] text-black px-4 py-2 rounded hover:bg-[#92c7ba]"
              onClick={handleUpload}
            >
              Starten
            </Button>

            {uploading && <div className="w-full bg-gray-200 rounded h-2"><div className="bg-[#78b2a7] h-2 rounded" style={{ width: `${progress}%` }}></div></div>}

            {resultUrl && (
              <div className="pt-4">
                <a
                  href={resultUrl}
                  className="underline text-[#78b2a7]"
                  download
                >
                  Ergebnis herunterladen
                </a>
              </div>
            )}

            {error && <p className="text-red-500 pt-4">{error}</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
