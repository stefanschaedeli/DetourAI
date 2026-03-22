# DESIGN_GUIDELINE.md

## Travel & Roadtrip — Apple-Inspired Design System

> *Klarheit. Reduktion. Tiefe.*
> Ein Design-System, das die ikonische Apple-Ästhetik auf Travel- und Roadtrip-Erlebnisse überträgt.

---

## 1. Design-Philosophie

### Kernprinzipien

| Prinzip | Beschreibung |
|---|---|
| **Reduktion** | Jedes Element muss seinen Platz verdienen. Weniger ist radikal mehr. |
| **Inhalt zuerst** | Bilder und Typografie erzählen die Geschichte — UI tritt zurück. |
| **Tiefe durch Einfachheit** | Subtile Schatten, sanfte Blur-Effekte und Layering statt dekorativer Ornamente. |
| **Emotionale Präzision** | Jede Sektion soll ein Gefühl auslösen — Fernweh, Freiheit, Staunen. |

### Ästhetische DNA

```
Apple-Prinzip          →  Travel-Adaption
─────────────────────────────────────────────────
Hero-Produktshot       →  Immersives Landscape-Vollbild
Produktdetail-Zoom     →  Drohnen-Perspektive / Detail-Close-Up
Feature-Highlights     →  Reise-Etappen / Erlebnis-Highlights
Scroll-Storytelling    →  Die Reise als narrativer Scroll-Pfad
Dark Mode Eleganz      →  Nacht-/Dämmerungsszenen auf der Strasse
```

---

## 2. Farbsystem

### Primärpalette

```css
:root {
  /* ── Hintergrund ── */
  --bg-primary:        #000000;       /* Tiefschwarz — Hero-Sections */
  --bg-secondary:      #111111;       /* Fast-Schwarz — Alternating Sections */
  --bg-surface:        #1d1d1f;       /* Apple Dark Surface */
  --bg-light:          #f5f5f7;       /* Apple Hellgrau — Kontrast-Sections */
  --bg-white:          #ffffff;       /* Reine Weiss-Sektionen */

  /* ── Text ── */
  --text-primary:      #f5f5f7;       /* Heller Text auf Dunkel */
  --text-secondary:    #a1a1a6;       /* Gedämpfter Subtext */
  --text-dark:         #1d1d1f;       /* Dunkler Text auf Hell */
  --text-muted:        #86868b;       /* Tertiärer Text */

  /* ── Akzente — Travel ── */
  --accent-sky:        #0a84ff;       /* Klarer Himmel / Links */
  --accent-sunset:     #ff6f3c;       /* Sonnenuntergang-Orange */
  --accent-golden:     #ffb347;       /* Golden Hour */
  --accent-forest:     #30d158;       /* Waldgrün / Natur */
  --accent-ocean:      #5ac8fa;       /* Ozean-Türkis */
  --accent-dust:       #c4a77d;       /* Wüstenstaub / Desert */

  /* ── Gradient-Token ── */
  --gradient-dusk:     linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  --gradient-golden:   linear-gradient(180deg, #000000 0%, #1a0a00 40%, #3d1c00 100%);
  --gradient-aurora:   linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #162447 100%);
}
```

### Farbanwendung

- **Hero-Sektionen**: Immer `--bg-primary` (#000) mit grossformatigem Bild darüber
- **Feature-Sektionen**: Wechsel zwischen `--bg-primary` und `--bg-light`
- **Text auf Dunkel**: `--text-primary` für Headlines, `--text-secondary` für Body
- **Text auf Hell**: `--text-dark` für Headlines, `--text-muted` für Body
- **Akzente sparsam**: Nur für CTAs, Links und Highlight-Wörter verwenden
- **Kein Farbüberschuss**: Maximal 1 Akzentfarbe pro Section

---

## 3. Typografie

### Schriftarten

```css
/* Primär — Apple-nah, clean und modern */
@import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;500;600;700&display=swap');

/* Fallback — Verfügbar und Apple-nah */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
  --font-display:    'Plus Jakarta Sans', 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-body:       'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono:       'SF Mono', 'JetBrains Mono', monospace;
}
```

### Typografie-Skala

```css
/* ── Hero-Headlines ── */
.hero-headline {
  font-family: var(--font-display);
  font-size: clamp(48px, 8vw, 96px);
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.03em;
  color: var(--text-primary);
}

/* ── Section-Headlines ── */
.section-headline {
  font-family: var(--font-display);
  font-size: clamp(36px, 5vw, 64px);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.025em;
}

/* ── Sub-Headlines ── */
.sub-headline {
  font-family: var(--font-display);
  font-size: clamp(20px, 2.5vw, 28px);
  font-weight: 500;
  line-height: 1.3;
  letter-spacing: -0.01em;
  color: var(--text-secondary);
}

/* ── Body ── */
.body-text {
  font-family: var(--font-body);
  font-size: clamp(16px, 1.2vw, 19px);
  font-weight: 400;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* ── Overline / Label ── */
.overline {
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent-sky);
}
```

### Typografie-Regeln

- Headlines immer **negatives Letter-Spacing** (`-0.02em` bis `-0.04em`)
- Body-Text immer **grosszügige Line-Height** (`1.5`–`1.7`)
- **Nie mehr als 2 Schriftgrössen** pro sichtbarem Viewport
- Overlines in Akzentfarbe, uppercase, mit weitem Tracking
- **Zentrierte Ausrichtung** für Hero- und Feature-Texte (Apple-Standard)
- Linksbündig nur in Content-Grids und Detail-Sektionen

---

## 4. Layout & Spacing

### Grid-System

```css
.container {
  width: 100%;
  max-width: 980px;        /* Apple Standard-Content-Breite */
  margin: 0 auto;
  padding: 0 24px;
}

.container--wide {
  max-width: 1200px;       /* Für Feature-Grids */
}

.container--full {
  max-width: 100%;         /* Für Hero-Images, Edge-to-Edge */
  padding: 0;
}
```

### Vertikaler Rhythmus

```css
:root {
  --space-xs:    8px;
  --space-sm:    16px;
  --space-md:    24px;
  --space-lg:    48px;
  --space-xl:    80px;
  --space-2xl:   120px;
  --space-3xl:   200px;

  /* Section-Abstände — grosszügig wie bei Apple */
  --section-gap:         var(--space-3xl);    /* 200px zwischen Sektionen */
  --section-gap-mobile:  var(--space-xl);     /* 80px auf Mobile */
}
```

### Spacing-Regeln

- **Grosszügige Weissräume** — Sections brauchen Luft zum Atmen (min. 120px Abstand)
- **Asymmetrische Anordnung** für Feature-Grids — nicht alles zentriert
- Bilder dürfen aus dem Container **ausbrechen** (full-bleed)
- **Sticky-Elemente** für Scroll-basiertes Storytelling nutzen
- Mobile: Single-Column, alles zentriert, keine Seitenlayouts

---

## 5. Bild- & Medienrichtlinien

### Bildsprache — Travel & Roadtrip

#### Motive & Themen

```
HERO-BILDER (Vollformat, immersiv):
├── Endlose Highways mit Fluchtpunkt-Perspektive
├── Panorama-Landschaften bei Golden Hour / Blue Hour
├── Drohnenaufnahmen von Küstenstrassen (z.B. Pacific Coast Highway)
├── Nebelverhangene Bergpässe im Morgengrauen
└── Wüstenstrassen mit dramatischem Himmel

FEATURE-BILDER (Detailreich, emotional):
├── Vanlife-Szenen: Kaffee am offenen Kofferraum
├── Landkarten und Reiseplanung auf Holztisch
├── Close-Up: Hände am Lenkrad, Fenster offen
├── Camping unter Sternenhimmel
├── Lokale Küche und Strassenmärkte
└── Vintage-Camper vor Naturkulisse

DETAIL-BILDER (Klein, atmosphärisch):
├── Kompass, Wanderschuhe, Rucksack
├── Notizbuch mit handgeschriebenen Reiserouten
├── Sonnenbrille auf dem Armaturenbrett
├── Reifenspuren im Sand / Schotter
└── Sticker auf einem Reisekoffer
```

#### Bildbehandlung

```css
/* ── Immersive Hero-Bilder ── */
.hero-image {
  width: 100%;
  height: 100vh;
  object-fit: cover;
  object-position: center 30%;     /* Himmel betonen */
}

/* ── Apple-typischer Bild-Fade über dunklem Hintergrund ── */
.hero-image-overlay {
  background: linear-gradient(
    to bottom,
    transparent 40%,
    rgba(0, 0, 0, 0.4) 70%,
    rgba(0, 0, 0, 1) 100%
  );
}

/* ── Feature-Bilder mit abgerundeten Ecken ── */
.feature-image {
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

/* ── Parallax-Effekt (subtil) ── */
.parallax-image {
  transform: translateZ(0);
  will-change: transform;
  transition: transform 0.1s linear;
}
```

#### Bildregeln

- **Keine Stockfoto-Ästhetik** — Bilder müssen authentisch wirken
- **Warme Farbtöne** bevorzugen: Golden Hour, Sunset, warmes Tageslicht
- **Hoher Kontrast** bei Hero-Bildern für Lesbarkeit des Texts
- **Keine Gesichter im Fokus** — Landschaft und Erlebnis stehen im Zentrum
- **Konsistente Farbstimmung** innerhalb einer Page: entweder warm ODER kühl
- Bilder **nie kleiner als 50% Viewport-Breite** — Apple denkt gross
- **Aspect Ratios**: Hero = 16:9 oder Vollbild, Features = 4:3 oder 3:2

### Video-Richtlinien

```css
.hero-video {
  width: 100%;
  height: 100vh;
  object-fit: cover;
  filter: brightness(0.7);        /* Leicht abgedunkelt für Text-Overlay */
}
```

- Autoplay, muted, loop für Hintergrundvideos
- Drohnenflüge über Landschaften als Hero-Video
- Zeitraffer von Sonnenuntergängen für Transitions
- Max. 10–15 Sekunden Loop

---

## 6. Komponenten

### Navigation

```css
.nav {
  position: fixed;
  top: 0;
  width: 100%;
  height: 48px;                    /* Apple-Standard */
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  background: rgba(0, 0, 0, 0.72);
  z-index: 1000;
  transition: background 0.3s ease;
}

.nav-link {
  font-family: var(--font-body);
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
  text-decoration: none;
  letter-spacing: 0.01em;
  transition: color 0.2s ease;
}

.nav-link:hover {
  color: var(--text-primary);
}
```

### Buttons / CTAs

```css
/* ── Primärer CTA — Apple Link-Style ── */
.cta-primary {
  font-family: var(--font-body);
  font-size: 19px;
  font-weight: 500;
  color: var(--accent-sky);
  background: none;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: color 0.2s ease;
}

.cta-primary::after {
  content: '›';
  font-size: 22px;
  transition: transform 0.2s ease;
}

.cta-primary:hover::after {
  transform: translateX(4px);
}

/* ── Sekundärer CTA — Pill-Button ── */
.cta-secondary {
  font-family: var(--font-body);
  font-size: 17px;
  font-weight: 500;
  color: var(--text-primary);
  background: var(--accent-sky);
  border: none;
  border-radius: 980px;           /* Apple Pill-Form */
  padding: 12px 28px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.cta-secondary:hover {
  background: #409cff;
}
```

### Karten (Feature Cards)

```css
.feature-card {
  background: var(--bg-surface);
  border-radius: 20px;
  overflow: hidden;
  transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.feature-card:hover {
  transform: scale(1.02);
}

.feature-card__image {
  width: 100%;
  aspect-ratio: 3 / 2;
  object-fit: cover;
}

.feature-card__content {
  padding: var(--space-lg);
}

.feature-card__title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}

.feature-card__description {
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.5;
  color: var(--text-secondary);
}
```

---

## 7. Animation & Motion

### Grundprinzipien

- **Subtilität** — Animationen unterstützen, dominieren nie
- **Physik-basiert** — Cubic-Bezier statt lineare Übergänge
- **Scroll-getrieben** — Elemente erscheinen beim Scrollen
- **Performance** — Nur `transform` und `opacity` animieren

### Easing-Kurven

```css
:root {
  --ease-apple:       cubic-bezier(0.25, 0.46, 0.45, 0.94);
  --ease-out-expo:    cubic-bezier(0.16, 1, 0.3, 1);
  --ease-spring:      cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

### Scroll-Animationen

```css
/* ── Fade-In beim Scrollen ── */
.reveal {
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.8s var(--ease-apple),
              transform 0.8s var(--ease-apple);
}

.reveal.visible {
  opacity: 1;
  transform: translateY(0);
}

/* ── Gestaffeltes Erscheinen ── */
.stagger > *:nth-child(1) { transition-delay: 0.0s; }
.stagger > *:nth-child(2) { transition-delay: 0.1s; }
.stagger > *:nth-child(3) { transition-delay: 0.2s; }
.stagger > *:nth-child(4) { transition-delay: 0.3s; }

/* ── Parallax-Scroll (CSS-only) ── */
.parallax-container {
  perspective: 1px;
  height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
}

.parallax-layer--back {
  transform: translateZ(-1px) scale(2);
}
```

### Micro-Interactions

```css
/* ── Hover-Lift für Karten ── */
.lift-on-hover {
  transition: transform 0.4s var(--ease-apple),
              box-shadow 0.4s var(--ease-apple);
}

.lift-on-hover:hover {
  transform: translateY(-8px);
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.4);
}

/* ── Image-Zoom bei Hover ── */
.zoom-on-hover {
  overflow: hidden;
  border-radius: 20px;
}

.zoom-on-hover img {
  transition: transform 0.6s var(--ease-apple);
}

.zoom-on-hover:hover img {
  transform: scale(1.05);
}
```

---

## 8. Seitenstruktur — Blueprint

### Typische Apple-Style Travel Page

```
┌─────────────────────────────────────────────┐
│  ▪ Nav (fixed, transluzent, 48px)           │
├─────────────────────────────────────────────┤
│                                             │
│  ████████████████████████████████████████   │
│  ████████  HERO FULLSCREEN IMAGE  ██████   │
│  ████████  (Highway / Landschaft)  █████   │
│  ████████████████████████████████████████   │
│                                             │
│         [ Grosse zentrierte Headline ]       │
│         [ Subtile Sub-Headline ]            │
│                                             │
├─ - - - - - - - - - - - - - - - - - - - - - ┤  ← 200px Abstand
│                                             │
│     OVERLINE: DIE REISE                     │
│     Section Headline (gross, zentriert)     │
│     Body-Text (max. 600px breit)            │
│                                             │
│     ┌──────────┐  ┌──────────┐              │
│     │  Bild 1  │  │  Bild 2  │              │
│     │ Feature  │  │ Feature  │              │
│     └──────────┘  └──────────┘              │
│                                             │
├─ - - - - - - - - - - - - - - - - - - - - - ┤  ← bg wechselt
│                                             │
│  ████████████████████████████████████████   │
│  ██████  FULL-BLEED LANDSCAPE  █████████   │
│  ████████████████████████████████████████   │
│                                             │
│     Zitat oder Key-Statement                │
│     (gross, zentriert, kursiv)              │
│                                             │
├─ - - - - - - - - - - - - - - - - - - - - - ┤
│                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │ Card 1  │ │ Card 2  │ │ Card 3  │      │
│  │ Etappe  │ │ Etappe  │ │ Etappe  │      │
│  └─────────┘ └─────────┘ └─────────┘      │
│                                             │
├─ - - - - - - - - - - - - - - - - - - - - - ┤
│                                             │
│          Abschluss-Headline                 │
│          CTA: Reise starten ›               │
│                                             │
├─────────────────────────────────────────────┤
│  Footer (minimal, dunkel)                   │
└─────────────────────────────────────────────┘
```

---

## 9. Responsive Breakpoints

```css
/* ── Mobile First ── */

/* Small phones */
@media (min-width: 375px)  { /* Base styles */ }

/* Large phones */
@media (min-width: 480px)  { /* Slightly larger text */ }

/* Tablets */
@media (min-width: 768px)  {
  /* 2-column grids, grössere Headlines */
}

/* Small desktop */
@media (min-width: 1024px) {
  /* 3-column grids, volle Hero-Erfahrung */
}

/* Desktop */
@media (min-width: 1280px) {
  /* Max-Width Container greifen */
}

/* Large screens */
@media (min-width: 1440px) {
  /* Grössere Typografie-Skalierung */
}
```

### Responsive-Regeln

- Hero-Bilder: Immer `100vw`, auf Mobile `60vh` statt `100vh`
- Headlines skalieren via `clamp()` — nie feste `px` auf Mobile
- Feature-Grid: 3 Spalten → 2 → 1 (nie 4+ Spalten)
- Navigation: Hamburger-Menü unter `768px`
- Bilder: `<picture>` mit `srcset` für Retina/Mobile

---

## 10. Performance & Technik

### Bildoptimierung

```html
<!-- WebP mit Fallback -->
<picture>
  <source srcset="highway-hero.webp" type="image/webp">
  <source srcset="highway-hero.jpg" type="image/jpeg">
  <img src="highway-hero.jpg"
       alt="Endloser Highway durch die Wüste bei Sonnenuntergang"
       loading="lazy"
       decoding="async"
       width="1920" height="1080">
</picture>
```

### Performance-Checkliste

```
☐  Bilder in WebP/AVIF servieren
☐  Lazy Loading für alles unter dem Fold
☐  Preload für Hero-Bild: <link rel="preload">
☐  Font-Display: swap für Web Fonts
☐  Kritisches CSS inline, Rest async laden
☐  Animationen nur transform + opacity
☐  prefers-reduced-motion respektieren
☐  Lighthouse Score > 90 in allen Kategorien
```

### Barrierefreiheit

```css
/* ── Reduced Motion ── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- Alle Bilder mit beschreibendem `alt`-Text
- Kontrastverhältnis mindestens **4.5:1** für Body, **3:1** für Headlines
- Fokus-Styles für Keyboard-Navigation
- Semantisches HTML: `<nav>`, `<main>`, `<section>`, `<article>`

---

## 11. Do's & Don'ts

### ✅ Do

- Grosse, immersive Bilder verwenden, die Fernweh auslösen
- Grosszügigen Weissraum lassen — Sections brauchen Luft
- Text zentrieren und kurz halten (max. 3–4 Zeilen pro Absatz)
- Dunkle Hintergründe für Hero-Sektionen mit heller Schrift
- Einheitliche Farbstimmung pro Seite (warm ODER kühl)
- Subtle Scroll-Animationen für Engagement
- Pill-Buttons für CTAs, Link-Style für sekundäre Actions

### ❌ Don't

- Kein Überdesign: Keine Borders, keine Box-Shadows auf Text
- Keine Stockfoto-Wasserzeichen oder generische Reisebilder
- Keine bunten Gradients als Hintergründe (nur fotografisch)
- Nie mehr als 2 Fonts gleichzeitig einsetzen
- Keine Textblöcke über 600px Breite
- Kein Parallax-Overload — maximal 1–2 Parallax-Elemente pro Page
- Keine Sidebar-Layouts — Apple denkt vertikal
- Keinen Content hinter Tabs oder Akkordeons verstecken

---

## 12. Referenz-Keywords für Bildsuche

Für konsistente Bildsprache folgende Suchbegriffe verwenden:

```
Landscapes:       "aerial highway drone", "mountain pass road fog",
                   "coastal road sunset", "desert road vanishing point"

Vanlife:          "campervan nature morning coffee", "rooftop tent starry sky",
                   "vintage van coastal road"

Details:          "travel flat lay map compass", "steering wheel open window",
                   "hiking boots mountain trail", "campfire lakeside night"

Atmosphäre:       "golden hour road trip", "blue hour mountain landscape",
                   "misty forest road morning", "dramatic sky open road"
```

---

*Letzte Aktualisierung: März 2026*
*Version: 1.0*
