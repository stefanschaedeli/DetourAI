# Lokales LLM mit Ollama — Setup-Anleitung

## Überblick

[Ollama](https://ollama.com) ist ein lokaler LLM-Server, der Sprachmodelle direkt auf deiner eigenen Hardware ausführt und eine OpenAI-kompatible REST-API anbietet. DetourAI unterstützt Ollama als Alternative zur Anthropic Claude API: alle KI-Agenten (Routenplanung, Unterkunftssuche, Tagesplanung usw.) laufen dann lokal, ohne dass Anfragen an externe Server gesendet werden. Das ist nützlich, wenn du Datenschutz priorisierst, API-Kosten sparen möchtest oder offline arbeiten willst.

---

## Modell-Empfehlungen

| Modell | RAM-Bedarf | Geschwindigkeit | Qualität | Empfohlen für |
|--------|-----------|----------------|----------|---------------|
| `qwen3:32b` (Q4) | ~20 GB | mittel (Mac M5) / langsam (CPU) | sehr gut | Mac M5 Air 32 GB, TrueNAS CPU-only |
| `qwen3:14b` (Q4) | ~9 GB | gut | gut | Mac M5 Air, TrueNAS CPU (T1000 VRAM reicht nicht) |
| `qwen3:8b` (Q4) | ~5 GB | schnell | ausreichend | TrueNAS T1000 GPU, schnelles Testen |

> **Hinweis zum TrueNAS T1000:** Die NVIDIA T1000 hat nur 4 GB VRAM. Qwen3 32B und 14B passen nicht vollständig in den VRAM und laufen daher hauptsächlich auf der CPU (langsamer, aber funktional). Qwen3 8B passt teilweise in den VRAM und profitiert noch am meisten vom GPU-Offloading. Für akzeptable Geschwindigkeit auf dem TrueNAS-Server wird `qwen3:8b` empfohlen.

---

## Mac-Setup (M5 Air, 32 GB)

### Installation

```bash
brew install ollama
```

### Modell herunterladen

```bash
ollama pull qwen3:32b
```

> ~20 GB Download. Während der Inferenz werden ebenfalls ~20 GB RAM belegt. Der Download kann je nach Verbindung 10–30 Minuten dauern.

Alternativ für ein kleineres Modell:

```bash
ollama pull qwen3:14b
# oder
ollama pull qwen3:8b
```

### Server starten

```bash
ollama serve
```

Der Server läuft standardmäßig auf Port **11434** und ist unter `http://localhost:11434` erreichbar. Der Prozess kann im Hintergrund laufen bleiben (z. B. als macOS-Dienst via `brew services start ollama`).

### In DetourAI konfigurieren

1. DetourAI öffnen → **Einstellungen** → **Lokales LLM**
2. Toggle **„Lokales LLM aktivieren"** einschalten
3. **Endpunkt:** `http://localhost:11434/v1/`
4. **Modell:** `qwen3:32b` (oder das heruntergeladene Modell)
5. Auf **„Verbindung testen"** klicken — bei Erfolg erscheint eine grüne Bestätigung

---

## TrueNAS-Setup (Docker-Container)

### Voraussetzungen

- Docker und Docker Compose auf dem TrueNAS-Host verfügbar
- Für GPU-Nutzung: [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) auf dem TrueNAS-Host installiert

### Docker Compose Konfiguration

Folgendes Snippet in eine `docker-compose.yml` auf dem TrueNAS-Server einfügen:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
    # NVIDIA GPU-Durchleitung (T1000) — entfernen, wenn kein NVIDIA Container Toolkit installiert ist:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped

volumes:
  ollama_data:
```

Container starten:

```bash
docker compose up -d
```

### Modell herunterladen

```bash
docker exec ollama ollama pull qwen3:32b
```

Für bessere Performance auf der T1000 (8B passt teilweise in den VRAM):

```bash
docker exec ollama ollama pull qwen3:8b
```

### Firewall

Port **11434** muss in der TrueNAS-Firewall geöffnet sein, damit der Mac auf den Server zugreifen kann. Überprüfe dies in der TrueNAS-Weboberfläche unter **Network → Firewall** oder mit:

```bash
# Vom Mac aus testen (TrueNAS-IP anpassen):
curl http://192.168.1.100:11434/api/tags
```

Eine JSON-Antwort mit den verfügbaren Modellen bestätigt die Verbindung.

### In DetourAI konfigurieren

1. DetourAI öffnen → **Einstellungen** → **Lokales LLM**
2. Toggle **„Lokales LLM aktivieren"** einschalten
3. **Endpunkt:** `http://<TrueNAS-IP>:11434/v1/` (z. B. `http://192.168.1.100:11434/v1/`)
4. **Modell:** `qwen3:32b` (oder `qwen3:8b` für bessere Geschwindigkeit)
5. Auf **„Verbindung testen"** klicken

---

## Leistung & Erwartungen

| Hardware | Modell | Geschwindigkeit | Planungsdauer (Roadtrip) |
|----------|--------|----------------|--------------------------|
| Mac M5 Air 32 GB | Qwen3 32B (Q4) | ~8–15 Token/s (Metal GPU) | ~3–8 Minuten |
| Mac M5 Air 32 GB | Qwen3 14B (Q4) | ~15–25 Token/s | ~1,5–4 Minuten |
| TrueNAS AMD 16-Core | Qwen3 32B (CPU) | ~2–5 Token/s | ~10–25 Minuten |
| TrueNAS T1000 + CPU | Qwen3 8B | ~5–10 Token/s | ~3–7 Minuten |

> **Zum Vergleich:** Die Anthropic Claude API liefert typischerweise 50–100 Token/s. Lokale Modelle sind langsamer, aber vollständig privat und kostenlos nach der einmaligen Hardware-Investition.

**Qualität der JSON-Ausgabe:** Qwen3 befolgt JSON-only-Anweisungen zuverlässig. Gelegentliches Markdown-Wrapping (z. B. ` ```json ... ``` `) wird von DetourAIs Parser automatisch erkannt und entfernt.

---

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| „Verbindung testen" schlägt fehl (Mac) | `ollama serve` läuft? `curl http://localhost:11434/api/tags` im Terminal testen |
| „Verbindung testen" schlägt fehl (TrueNAS) | Port 11434 in Firewall geöffnet? `OLLAMA_HOST=0.0.0.0` in Docker env gesetzt? IP-Adresse korrekt? |
| Sehr langsame Antworten | Modell zu groß für verfügbaren RAM/VRAM → kleineres Modell wählen (`qwen3:8b` statt `32b`) |
| Prozess friert ein / Out of Memory | RAM-Verbrauch prüfen; auf dem Mac `Activity Monitor` öffnen; Modell-Quantisierung reduzieren |
| JSON-Fehler bei der Planung | `max_tokens` in den Einstellungen erhöhen; Qwen3 8B statt 32B versuchen; Modell neu laden: `ollama run qwen3:32b` |
| NVIDIA GPU wird nicht erkannt (Docker) | NVIDIA Container Toolkit installieren: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html |
| Modell lädt nicht (Docker) | Volume-Berechtigungen prüfen: `docker exec ollama ls /root/.ollama/models` |
| `ollama serve` startet nicht (Port belegt) | `lsof -i :11434` prüfen; laufende Instanz beenden: `pkill ollama` |
