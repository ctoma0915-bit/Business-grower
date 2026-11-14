from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
A="/home/user/business-grower/nord-roof/"
OUT=A+"social/"
F="/usr/share/fonts/opentype/inter/"
f=lambda n,s: ImageFont.truetype(F+n,s)
RED=(237,28,36); W,H=1080,1350
logo=Image.open(A+"logo.png").convert("RGBA")
def photo(src,box,size=(W,H)):
    im=Image.open(A+src).convert("RGB").crop(box).resize(size,Image.LANCZOS)
    return im.filter(ImageFilter.UnsharpMask(2,50,2))
def badge(img):
    lw=360; l=logo.resize((lw,int(logo.height*lw/logo.width)),Image.LANCZOS)
    d=ImageDraw.Draw(img); pad=22
    d.rounded_rectangle((40,40,40+lw+2*pad,40+l.height+2*pad),radius=18,fill=RED)
    img.paste(l,(40+pad,40+pad),l)
def portfolio(name,src,box,kick,title,top=False):
    # red/white style: red header with logo, photo, white panel, red bar
    img=Image.new("RGB",(W,H),(255,255,255)); d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,150),fill=RED)
    lw=380; l=logo.resize((lw,int(logo.height*lw/logo.width)),Image.LANCZOS); img.paste(l,((W-lw)//2,(150-l.height)//2),l)
    bw,bh=box[2]-box[0],box[3]-box[1]; ph=820
    # crop the source box to the photo slot's 1080:820 ratio, centred
    tw=bw; th=int(bw*ph/W)
    if th>bh: th=bh; tw=int(bh*W/ph)
    cx,cy=box[0]+bw//2,(box[1]+th//2 if top else box[1]+bh//2)
    img.paste(photo(src,(cx-tw//2,cy-th//2,cx+tw//2,cy+th//2),(W,ph)),(0,150))
    k=f("Inter-Bold.otf",32); x=66
    for ch in kick:
        d.text((x,1018),ch,font=k,fill=RED); x+=d.textlength(ch,font=k)+3.5
    d.text((66,1066),title,font=f("InterDisplay-Bold.otf",66),fill=(20,20,20))
    d.text((66,1160),"București și Ilfov",font=f("Inter-Medium.otf",36),fill=(110,110,110))
    d.rectangle((0,H-90,W,H),fill=RED)
    d.text((W//2,H-45),"WhatsApp: 0726 981 090",font=f("Inter-Bold.otf",40),fill="white",anchor="mm")
    img.save(OUT+name,quality=92)
# clean photo regions (no old text)
portfolio("post-1-hala-tabla.jpg","ads/reclama-ad6-hale-4x5.jpg",(300,440,300+728,1350),"LUCRARE RECENTĂ","Acoperiș din tablă la hală")
portfolio("post-2-etansare-imbinari.jpg","ads/reclama-ad3-infiltratii-9x16.jpg",(110,642,110+862,1720),"LUCRARE RECENTĂ","Etanșare îmbinări și coamă")
portfolio("post-3-jgheaburi-sofit.jpg","ads/reclama-ad2-jgheaburi-9x16.jpg",(62,660,62+960,1860),"LUCRARE RECENTĂ","Jgheaburi, burlane și sofit")
portfolio("post-4-streasina-casa.jpg","ads/reclama-ad7-casa-noua-4x5.jpg",(170,0,170+728,910),"LUCRARE RECENTĂ","Streașină și jgheaburi",top=True)
portfolio("post-5-anexa.jpg","ads/reclama-ad8-cladiri-mici-4x5.jpg",(250,0,250+728,910),"ANEXE ȘI GARAJE","Jgheaburi la o anexă",top=True)
portfolio("post-6-casa-lemn.jpg","ads/reclama-ad1-iarna-9x16.jpg",(150,642,150+850,1704),"LUCRARE RECENTĂ","Acoperiș cu streașină din lemn")

# tips carousel
def slide(name,num,title,body,cover=False,cta=False):
    img=Image.new("RGB",(W,H),(255,255,255)); d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,150),fill=RED)
    lw=380; l=logo.resize((lw,int(logo.height*lw/logo.width)),Image.LANCZOS); img.paste(l,((W-lw)//2,(150-l.height)//2),l)
    if cover:
        p=photo("ads/reclama-ad3-infiltratii-9x16.jpg",(110,700,110+862,1240),(W,640)); img.paste(p,(0,150))
        d.text((66,850),"5 semne că acoperișul",font=f("InterDisplay-Bold.otf",72),fill=(20,20,20))
        d.text((66,936),"are nevoie de reparație",font=f("InterDisplay-Bold.otf",72),fill=RED)
        d.text((66,1060),"înainte să vă plouă în casă",font=f("Inter-Medium.otf",40),fill=(90,90,90))
        d.text((66,1240),"Glisați →",font=f("Inter-Bold.otf",40),fill=RED)
    else:
        if num: 
            d.ellipse((66,240,186,360),fill=RED); d.text((126,300),str(num),font=f("InterDisplay-Bold.otf",72),fill="white",anchor="mm")
        y=420
        for ln in title: d.text((66,y),ln,font=f("InterDisplay-Bold.otf",76),fill=(20,20,20)); y+=90
        y+=40
        for ln in body: d.text((66,y),ln,font=f("Inter-Regular.otf",42),fill=(70,70,70)); y+=62
        if cta:
            d.rounded_rectangle((66,1150,W-66,1260),radius=16,fill=RED)
            d.text((W//2,1205),"Scrieți-ne pe WhatsApp",font=f("Inter-Bold.otf",46),fill="white",anchor="mm")
        else:
            d.text((66,1240),"Glisați →",font=f("Inter-Bold.otf",40),fill=RED)
    img.save(OUT+name,quality=92)
slide("carusel-1.jpg",0,[],[],cover=True)
slide("carusel-2.jpg",1,["Pete de umezeală","pe tavan"],["Mai ales la ultimul etaj sau în colțuri.","Apa intră de obicei mult mai sus","decât apare pata."])
slide("carusel-3.jpg",2,["Tablă ruginită sau","șuruburi slăbite"],["Garniturile șuruburilor îmbătrânesc,","iar pe la găuri intră apa.","Se repară înainte să se extindă."])
slide("carusel-4.jpg",3,["Apă care curge","pe perete"],["Jgheaburi înfundate, fisurate","sau burlane desprinse.","Udă fațada și fundația."])
slide("carusel-5.jpg",4,["Îmbinări și atice","care nu mai țin"],["La hale și acoperișuri plate,","apa intră pe la îmbinări,","coame și atice."])
slide("carusel-6.jpg",5,["Bucăți mișcate","după vânt"],["Tablă ridicată, coame sau","șorțuri desprinse după furtună.","Verificați din curte, nu urcați."])
slide("carusel-7.jpg",None,["Vedeți unul","dintre semne?"],["Trimiteți-ne câteva poze","pe WhatsApp și adresa.","Revenim cu o ofertă de preț."],cta=True)
