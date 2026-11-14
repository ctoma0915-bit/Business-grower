# Acoperișul tău perfect

Texts for the Facebook page, Instagram account and WhatsApp Business profile of a roofing firm. Renamed from the earlier working name on 14 Nov 2026.

**The idea behind the texts:** the name promises a roof done properly, with nothing left to worry about. The texts describe what a good roof is and how easy it is to ask for a quote; they never promise prices, years in business or guarantees.

**Before publishing:**
- Area: București și Ilfov (confirmed by Toma, 13 Nov 2026).
- Customer number: 0728 636 383 (confirmed by Toma, 13 Nov 2026).
- Remove any service he doesn't offer (check *mansarde*, *dulgherie*, *termoizolație*).

## Brand

Files are in `brand/` (`sursa-brand.html` regenerates them):

| File | Use |
|---|---|
| `profil-1080.png` | Profile picture on Facebook, Instagram and WhatsApp Business (1080×1080, safe for the round crop) |
| `coperta-facebook-1640x624.png` | Facebook cover photo |
| `logo.png` | Main logo, dark text, transparent background |
| `logo-alb.png` | Logo with white text, transparent background, for dark photos and backgrounds |
| `simbol.svg` / `simbol-fundal-inchis.svg` | The symbol alone, as a vector, for light and dark backgrounds |

**The symbol:** a roof line with a **copper check mark** under it: the roof, done right.

**Colours**
- Slate `#2B3440`
- Copper: `#B8692A` on light backgrounds, `#E08A45` on dark ones
- White

**Font:** Plus Jakarta Sans (Google Fonts).
- "ACOPERIȘUL": ExtraBold 800.
- "TĂU PERFECT": SemiBold 600, spread to the same width as the word above, with "PERFECT" in copper.

## Facebook page

| Field | Text |
|---|---|
| Page name | Acoperișul tău perfect |
| Category | Roofing Service (Serviciu de acoperișuri), plus Contractor |
| Username | `acoperisultauperfect` (if taken: `acoperisul.tau.perfect`) |
| Bio (max 101 characters) | `Acoperișul tău perfect: montaj, reparații, jgheaburi. Sunați pentru ofertă: 0728 636 383` |
| Service area | București și Ilfov |
| Button | Call now (*Sunați acum*), number 0728 636 383 |

**Details / About:**
```
Acoperișul tău perfect se ocupă de tot ce ține de acoperișul casei dumneavoastră, de la prima evaluare până la ultimul detaliu.

Ce facem:
• Acoperișuri noi și înlocuiri de acoperiș
• Reparații și infiltrații
• Jgheaburi și burlane
• Mansarde, dulgherie, termoizolație

Cum cereți o ofertă:
1. Sunați-ne la 0728 636 383
2. Spuneți-ne localitatea și ce lucrare doriți
3. Vă spunem pașii următori și vă facem o ofertă

Preferați să scrieți? Trimiteți-ne poze pe WhatsApp: wa.me/40728636383

Zona: București și Ilfov.
```

## Instagram

| Field | Text |
|---|---|
| Name | Acoperișul tău perfect |
| Username | `acoperisultauperfect` (if taken: `acoperisul.tau.perfect`) |
| Category | Roofing Service |
| Contact button | Call (*Sunați*), number 0728 636 383. Instagram doesn't open phone links from the bio, so the call goes through this button. |
| Link | `https://wa.me/40728636383`, titled `Trimiteți poze pe WhatsApp`. One tap opens a WhatsApp chat with his number; the greeting message then asks for the photos. |

**Bio** (max 150 characters):
```
🏠 Acoperișul casei, făcut cum trebuie
Montaj · Reparații · Jgheaburi · Mansarde
📍 București și Ilfov
📞 Sunați pentru ofertă: 0728 636 383
```

## WhatsApp Business

- **Name:** Acoperișul tău perfect
- **Description:** same as the Facebook bio
- **Link to share anywhere** (posts, comments, ads): `wa.me/40728636383`. It's short and shows his number, so it doesn't look suspicious. The greeting message does the asking, so the link needs no pre-written text.
- **Greeting message:**
```
Bună ziua! Trimiteți-ne 2–3 poze cu acoperișul și localitatea. Vă sunăm noi cu detaliile.
```

### Short link with a ready-made form (optional)

In the WhatsApp Business app, the short link (`wa.me/message/…`) can carry a default message. Set it to this mini-form, so the customer only fills in the blanks and adds photos:

```
Bună ziua! Aș dori o ofertă pentru acoperiș.
📍 Localitatea:
🔧 Lucrarea (reparație / acoperiș nou / jgheaburi / altceva):
📷 Atașez mai jos 2–3 poze.
```

If the app doesn't keep the line breaks, use the one-line version:

```
Bună ziua! Aș dori o ofertă pentru acoperiș. Localitatea: … Lucrarea: … Atașez poze.
```

**Steps (on his phone, WhatsApp Business on 0728 636 383):**
1. ⋮ (Android) or Settings (iPhone) → Business tools → Short link.
2. Default message → paste the form above → turn on "Send default message" → Save.
3. Copy link. Use it instead of `wa.me/40728636383` on Facebook (Website field, About text) and Instagram (external link).
4. Never tap "Reset link": the old link would stop working everywhere.
5. Test it from another phone: the chat should open with the form already typed.

## Meta lead form (Instant Form)

Built from `../playbooks/meta-lead-form.md`. Create it in **business.facebook.com → All tools → Instant forms → Create form**, on the Acoperișul tău perfect page.

| Setting | Value |
|---|---|
| Form name | `Acoperișul tău perfect · Ofertă rapidă` |
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
   - `Îmi intră apa în casă`
   - `Acoperiș nou sau înlocuire`
   - `Reparație la acoperiș`
   - `Jgheaburi și burlane`
2. Prefill: **Full name**, **Phone number**. Nothing else (the ads target București și Ilfov; ask the address on the call).

**Privacy policy:** text `Politica de confidențialitate`, link `https://ctoma0915-bit.github.io/Business-grower/acoperisul-tau-perfect/confidentialitate/`

**Ending screen:**
- Headline: `Gata! Am primit cererea ✅`
- Description: `Vă sunăm noi astăzi, de pe 0728 636 383. Nu mai trebuie să faceți nimic.` (only if he really calls back the same day)
- Button: **Call business**, text `Sunați-ne acum`, number `+40 728 636 383`

After publishing, send Toma the **form ID**: the ads can't be built without it.

## Ads

Images in `reclame/` (1080×1350; `sursa.html` and `sursa-foto.html` regenerate them). He has no job photos yet: ads 1–3 are brand graphics, ads 4–5 use public-domain stock photos listed in `reclame/SURSE-FOTO.md`. The stock photos are illustrations only, never "lucrarea noastră". Replace them with his own photos as soon as he sends some.

| # | Image | Headline on image |
|---|---|---|
| 1 | `reclama-1-infiltratii.png` | Vă intră apa în casă? |
| 2 | `reclama-2-brand.png` | Tot ce ține de acoperiș, făcut cum trebuie. |
| 3 | `reclama-3-iarna.png` | Pregătiți acoperișul pentru iarnă. |
| 4 | `reclama-4-foto-acoperis-nou.png` | Acoperiș nou sau reparații? |
| 5 | `reclama-5-foto-iarna.png` | Schimbați acoperișul înainte de iarnă. |

**Primary texts:**
- Leak: `Vă intră apa în casă? Trimiteți-ne cererea și vă spunem ce e de făcut la acoperiș.`
- Brand: `Acoperiș nou, reparații, jgheaburi: ne ocupăm de tot, ca acoperișul să fie exact cum trebuie.`
- Winter: `Verificați acoperișul înainte de iarnă. Reparăm acum, nu după prima ploaie.`

All end with: `👉 Apăsați „Obțineți ofertă”: numele și telefonul se completează singure. Durează 5 secunde.`

## First 3 posts (before any ads, so the page doesn't look empty)

Use only his real photos and jobs. Don't invent numbers, years or guarantees.

1. **Introduction:** a photo of his team or of a finished roof, plus:
   ```
   Acoperișul tău perfect: ne ocupăm de tot ce ține de acoperișul casei, de la prima evaluare până la ultimul detaliu. Montaj, reparații, jgheaburi, mansarde. Sunați-ne la 0728 636 383 și vă spunem ce e de făcut.
   ```
2. **What "perfect" means:** a photo of a roof in progress, plus:
   ```
   Cum arată un acoperiș perfect?
   ✔ Nu plouă înăuntru, nici la ploi mari
   ✔ Jgheaburile duc apa departe de casă
   ✔ Țigla sau tabla stau bine prinse la vânt
   ✔ Arată bine și după ani de zile
   Asta urmărim la fiecare acoperiș. Sunați-ne pentru o ofertă: 0728 636 383
   ```
3. **A finished job:** before and after photos, plus:
   ```
   Acoperiș refăcut în [localitate]. [Material] și jgheaburi noi, fără grija clientului.
   ```

## Next steps

1. He creates the Facebook page, Instagram account and WhatsApp Business profile with these texts, then adds Toma as a page admin. Alternatively, Toma creates them and gives him access.
2. Upload `brand/profil-1080.png` as the profile picture and `brand/coperta-facebook-1640x624.png` as the Facebook cover.
3. Lead form and ads: follow `../playbooks/meta-lead-form.md`.
4. **Overlap:** other roofing clients already advertise in București and Ilfov. If he works there too, Toma decides how to split the area.
