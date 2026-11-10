# Meta lead form ads (Instant Forms): reusable playbook

Use this for any client who wants requests from Facebook and Instagram ads: roofing, windows, renovations or any local service. Replace every `[PLACEHOLDER]` with the client's details. Write the form texts in Romanian, exactly as below.

## Why form ads

In our first test for a local service business (2026), form ads clearly beat WhatsApp ads:
- **Form ads:** 15 requests for about 130 lei. The best ad cost about 5 lei per request.
- **WhatsApp ads:** people tapped them, but almost nobody started a chat.

So start new clients on form ads. Add WhatsApp ads only as a small extra, if at all.

## 1. Fill in these details first

| Placeholder | Example |
|---|---|
| `[FIRMA]` | name of the client's page |
| `[SERVICII]` | Reparații, infiltrații, acoperiș nou, jgheaburi |
| `[ZONA]` | București și Ilfov / toată România |
| `[OFERTA]` | Evaluare gratuită la fața locului |
| `[TELEFON]` | +40 7xx xxx xxx |
| `[LINK_CONFIDENTIALITATE]` | a public privacy page (we can host it on this repo's GitHub Pages) |

## 2. Create the form (the client does this; our Meta tools can't)

Create it in **business.facebook.com → All tools → Instant forms → Create form**. If Meta asks, accept the **Lead Ads Terms**. Once published, a form can't be edited, only copied, so check the texts before publishing.

**Form name** (only the client sees it): `[FIRMA] · Cerere ofertă`

**Form type:** **Higher intent** ("Intenție mai mare"). It adds a review screen where people confirm their phone number, which means fewer wrong numbers.

**Intro**
- **Image:** the ad's image.
- **Headline:** `Ofertă pentru [SERVICIU PRINCIPAL] în [ZONA]`
- **Description** (bullet list, one line each):
  ```
  [SERVICII]
  [OFERTA]
  Vă contactăm noi pe WhatsApp sau la telefon
  ```

**Questions**, in this order:
1. **Custom question → Multiple choice:** `Ce lucrare doriți?`. Answers by trade:

   | Trade | Answers |
   |---|---|
   | Roofing | `Reparație / infiltrații` · `Acoperiș nou / înlocuire` · `Jgheaburi și burlane` · `Altceva` |
   | Windows | `Ferestre noi` · `Înlocuire ferestre vechi` · `Uși de exterior` · `Altceva` |
   | Renovations | `Renovare completă` · `Baie / bucătărie` · `Zugrăveli / finisaje` · `Altceva` |

   Keep it to 3 or 4 answers, and always end with `Altceva`.
2. **Custom question about the location:** `Unde este lucrarea?`
   - **Local client:** multiple choice with the client's area, for example `București` · `Ilfov` · `Altă zonă`.
   - **National client:** short answer, with the hint `Localitatea și județul`.
3. **Prefill questions:** **Full name** and **Phone number** only.

   Don't add email or anything else: every extra field loses people.

**Questions description** (if there's a box for it): `Durează 10 secunde. Numele și telefonul sunt deja completate.`

**Privacy policy**
- Link text: `Politica de confidențialitate`
- Link: `[LINK_CONFIDENTIALITATE]`

**Ending screen**
- **Headline:** `Mulțumim! Am primit cererea.`
- **Description:** `Vă contactăm în curând pe WhatsApp sau la telefon. Nu mai trebuie să faceți nimic.`
- **Button:** **Call business**, text `Sunați-ne acum`, number `[TELEFON]`.

**Settings:** language Romanian; sharing **Restricted**.

**Contact information:** the form doesn't need a field for this. The client's phone goes on the ending button, and the first message to each lead says "we'll contact you on WhatsApp or by phone". A WhatsApp text works as the first contact.

When it's published, ask the client for the **form ID**. Ads can't be created without it.

## 3. Build the ads (Meta Ads tools)

**Campaign**
- **Objective:** leads.
- **Keep it separate:** a form campaign can't share a campaign with WhatsApp ads.
- **Overlapping clients:** clients in the same trade and area each get their own campaign, form and lead codes.

**Ad set**
- Optimization **LEAD_GENERATION**, destination **ON_AD**.
- The client's page, the Instagram account if connected, and the radius or regions of `[ZONA]`.

**Creative**
- `link_data.link`: `"http://fb.me/"`.
- `call_to_action`: `{"type":"GET_QUOTE","value":{"lead_gen_form_id":"<FORM ID>"}}`.
- Without the form ID, the ad fails with "Missing Lead Form".

**Ads**
- Make 3 to 5, each with a different photo and angle: a problem like leaks, a finished job, a review, a seasonal hook like "before winter", and a price or free visit.
- Use the client's real photos.

**Budget**
- **Amounts:** budgets are in minor units (2000 = 20 lei/day). Start at 15 to 20 lei/day.
- **After editing:** changing a budget can pause the campaign. Check it's active again afterwards.

**Launch:** create everything paused, check the preview, then activate.

## 4. Handling the leads

**Where they appear**
- Requests only appear in **Meta Business Suite → Leads Center**.
- Meta doesn't email them, and our Meta tools can't read them.
- Tell the client to turn on lead notifications in the Business Suite app.
- To work on leads in a chat, paste a screenshot or the Leads Center download.

**Automatic copy into a sheet (optional, free)**
- Make.com: **Facebook Lead Ads → Watch New Leads**, then **Google Sheets → Add a row** (or an HTTP request to the client's sheet).
- When Make.com asks for payment, choose the **Free** plan and don't start from a paid template. The free plan covers this volume.

**Speed:** contact each lead within minutes, on WhatsApp first. Leads go cold within hours.

**First WhatsApp message** (adapt it to the lead's answers):
```
Bună ziua, domnule/doamna [NUME]! Sunt [PRENUME], de la [FIRMA]. Ați completat formularul nostru pentru [LUCRARE]. Mulțumim!

Ca să vă putem da detalii și un preț corect, ne puteți trimite:
1. câteva poze cu [ZONA CU PROBLEMA / ce e de făcut]
2. [o întrebare despre lucrare, de ex. ce fel de acoperiș aveți / câte ferestre]
3. localitatea sau adresa aproximativă

[Evaluarea la fața locului este gratuită.] Ce zi și oră v-ar conveni să trecem?
```
Ask for photos and the address first, so the job can be priced before anyone travels.

## 5. Checking and optimizing

**When to judge:** check cost per request after 3 days. Meta usually pushes most of the budget to one ad.

**Weak ads:**
- **When to pause:** an ad has spent at least 3× the best ad's cost per request and costs at least 3× as much per request.
- **Pause, never delete.**

**When the account changes:** if another chat edits the account, check the activity log before deciding.

**Budget moves:** report them and get the client's or Toma's OK before changing anything.
