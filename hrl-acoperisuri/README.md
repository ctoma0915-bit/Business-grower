# HRL Acoperișuri

Brand kit and texts for the Facebook page, Instagram account and WhatsApp Business profile of a roofing and construction firm (roofs, standing-seam metal, modular houses, timber work, terraces, renovations). Added on 16 Nov 2026.

**The idea behind the texts:** short and practical. The customer sends a few photos, the town and the job, and gets an answer. The texts never promise prices, years in business, guarantees or numbers of jobs.

**Before publishing:**
- Area: all of Romania (confirmed by Toma, 18 Nov 2026; until then it was Oradea and Bihor).
- Customer number: 0738 049 791 (confirmed by Toma, 16 Nov 2026). It is used everywhere: buttons, WhatsApp link and About text.
- Services: the list below is the full list he gave Toma (16 Nov 2026). Don't add others.
- Posts: only his own photos and jobs. No stock photos presented as his work.

## Brand

Files are in `brand/` (`sursa-brand.html` regenerates them):

| File | Use |
|---|---|
| `profil-1080.png` | Profile picture on Facebook, Instagram and WhatsApp Business (1080×1080, safe for the round crop, readable down to 40 px) |
| `coperta-facebook-1640x624.png` | Facebook cover photo (everything important sits in the centre, so the mobile crop keeps it) |
| `logo.png` | Main logo, dark text, transparent background |
| `logo-alb.png` | Logo with white text, transparent background, for dark photos and backgrounds |
| `simbol.svg` / `simbol-fundal-inchis.svg` | The symbol alone, as a vector, for light and dark backgrounds |

**The symbol:** the **HRL** monogram in heavy block letters, sheltered under a single amber roof line. The letters are drawn as shapes, not typed, so the SVGs need no font.

**Colours**
- Petrol blue `#0E2F3C` (background, dark text)
- Amber: `#C68512` on light backgrounds, `#F5B83D` on dark ones
- White

**Font:** Archivo (Google Fonts).
- "HRL": Black 900.
- "ACOPERIȘURI": Bold 700, spread to the same width as "HRL", in amber.

## Facebook page

| Field | Text |
|---|---|
| Page name | HRL Acoperișuri |
| Category | Roofing Service (Serviciu de acoperișuri), plus Contractor and Home Improvement |
| Username | `hrlacoperisuri` (if taken: `hrl.acoperisuri`) |
| Bio (max 101 characters; this one is 84) | `Acoperișuri, tablă fălțuită, case modulare, terase și reabilitări, în toată România.` |
| Service area | Romania |
| Button | Send WhatsApp message (*Trimiteți mesaj pe WhatsApp*), number 0738 049 791 |

**Details / About:**
```
HRL Acoperișuri lucrează în toată România: în orașe, comune și sate.

Ce facem:
• Acoperișuri
• Tablă fălțuită
• Case modulare din lemn, din polistiren sau pe structură metalică
• Construcții din lemn
• Terase
• Reabilitări
• Lucrări la monumente istorice

Cum cereți o ofertă:
1. Trimiteți-ne pe WhatsApp câteva poze sau o schiță
2. Spuneți-ne localitatea
3. Spuneți-ne ce lucrare doriți
Vă răspundem cu pașii următori și o ofertă.

WhatsApp: wa.me/40738049791
Zona: toată România.
```

## Instagram

| Field | Text |
|---|---|
| Name | HRL Acoperișuri |
| Username | `hrl.acoperisuri` (if taken: `hrlacoperisuri`) |
| Category | Roofing Service |
| Link | `https://wa.me/40738049791`, titled `Trimiteți poze pe WhatsApp` |

**Bio** (max 150 characters; this one is 135, at most 141 if Instagram counts emoji as 2):
```
🏠 Acoperișuri · Tablă fălțuită · Case modulare
🪵 Construcții din lemn · Terase · Reabilitări
📍 În toată România 🇷🇴
📷 Poze pe WhatsApp 👇
```

## WhatsApp Business

- **Number:** 0738 049 791
- **Name:** HRL Acoperișuri
- **Profile picture:** `brand/profil-1080.png`
- **Category:** Home Improvement (*Îmbunătățiri pentru locuință*)
- **Description:**
```
Acoperișuri, tablă fălțuită, case modulare (lemn, polistiren, structură metalică), construcții din lemn, terase, reabilitări și monumente istorice. În toată România. Trimiteți-ne poze, localitatea și ce lucrare doriți, și vă răspundem cu o ofertă.
```
- **Greeting message:**
```
Bună ziua! Mulțumim pentru mesaj. Ca să vă putem da detalii și un preț corect, trimiteți-ne vă rog:
1. 2–3 poze cu acoperișul, casa sau locul lucrării
2. Localitatea
3. Ce lucrare doriți (acoperiș, tablă fălțuită, casă modulară, terasă, reabilitare sau altceva)
Vă răspundem cât mai repede.
```

## Meta lead form (Instant Form)

Built from `../playbooks/meta-lead-form.md`. Create it in **business.facebook.com → All tools → Instant forms → Create form**, on the HRL Acoperișuri page. Accept the Lead Ads Terms if Meta asks.

| Setting | Value |
|---|---|
| Form name | `HRL Acoperișuri · Ofertă rapidă` |
| Type | **More volume** (*Volum mai mare*) |
| Intro | Off. If Meta insists: ad image + headline `Ofertă gratuită în 5 secunde`, no description |
| Language | Romanian |
| Sharing | Restricted |

**Questions description:**
```
✅ Gratuit și fără obligații
✅ Numele și telefonul sunt deja completate
👉 Alegeți o variantă și apăsați Trimiteți
```

**Questions:**
1. Multiple choice, `Cu ce vă putem ajuta?`:
   - `Acoperiș nou sau tablă fălțuită`
   - `Reparație sau reabilitare`
   - `Casă modulară`
   - `Terasă sau construcție din lemn`
2. Prefill: **Full name**, **Phone number**. Because he works nationally, also add **City** (*Oraș*): it is prefilled, so it costs no typing. Nothing else.

**Privacy policy:** text `Politica de confidențialitate`, link `https://ctoma0915-bit.github.io/Business-grower/hrl-acoperisuri/confidentialitate/`

**Ending screen:**
- Headline: `Gata! Am primit cererea ✅`
- Description: `Vă contactăm noi în cel mai scurt timp. Nu mai trebuie să faceți nimic.`
- Button: **Call business**, text `Sunați-ne acum`, number `+40 738 049 791`

After publishing, send the **form ID**: the ads can't be built without it.

## Ads

Images are in `reclame/` (1080×1350; `sursa.html` regenerates them). All five use his own job photos (`foto-*.jpg`), which Toma confirmed can be used in ads. Customer photos from reviews are **not** used until those customers agree.

| # | Image | Photo | Headline on image |
|---|---|---|---|
| 1 | `reclama-1-acoperis-nou.png` | Metal tile and grey trapezoidal sheet roof | Acoperiș nou, oriunde în România? |
| 2 | `reclama-2-iarna.png` | Brown metal tile roof | Schimbați acoperișul înainte de iarnă. |
| 3 | `reclama-3-sarpante.png` | Timber roof trusses | Șarpante din lemn, de la zero. |
| 4 | `reclama-4-romania.png` | Team laying red tiles | Acoperișuri noi, în toată țara. |
| 5 | `reclama-5-lemn-terase.png` | Timber structure being built | Construcții din lemn și terase. |

No modular-house ad yet: there is no photo of one. Add it when he sends one.

## First 3 posts (before any ads, so the page doesn't look empty)

Use only his real photos and jobs. Don't invent numbers, years or guarantees. Fill the brackets from what he tells you about each job.

1. **Introduction:** a photo of a job he finished (or the cover image if he has none yet), plus:
   ```
   Bine ați venit la HRL Acoperișuri! Facem acoperișuri, tablă fălțuită, case modulare, construcții din lemn, terase și reabilitări, în toată România. Trimiteți-ne pe WhatsApp câteva poze și vă spunem ce e de făcut: wa.me/40738049791
   ```
2. **A finished job:** his own before and after photos, plus:
   ```
   Înainte și după, în [localitate]. [Ce s-a făcut: de ex. acoperiș din tablă fălțuită / casă modulară din lemn / terasă / reabilitare]. Vă gândiți la ceva asemănător? Trimiteți-ne poze pe WhatsApp.
   ```
3. **What to check before winter:** his own photo of a roof or gutters, plus:
   ```
   Înainte de iarnă, aruncați o privire la acoperiș:
   ✔ țigle sau tablă desprinse
   ✔ jgheaburi înfundate cu frunze
   ✔ pete de umezeală pe tavan
   Vedeți ceva din toate acestea? Trimiteți-ne poze pe WhatsApp și vă spunem ce e de făcut.
   ```

## Next steps

1. He (or Toma, with access for him) creates the Facebook page, Instagram account and WhatsApp Business profile with these texts, then adds Toma as a page admin.
2. Upload `brand/profil-1080.png` as the profile picture and `brand/coperta-facebook-1640x624.png` as the Facebook cover.
3. Lead form and ads: follow `../playbooks/meta-lead-form.md`. Target all of Romania except București and Ilfov, where other roofing clients already advertise, unless Toma decides otherwise.
