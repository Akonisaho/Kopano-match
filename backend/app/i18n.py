"""The platform's own explanations, in four languages.

Every sentence the engine's explanation uses is a fixed template, so it translates exactly: no AI is
involved, nothing is guessed, and the numbers inside never change. That is why a business reads the same
facts whatever its language.

Afrikaans is reviewed. isiZulu and Sesotho are drafts and MUST be checked by a first-language speaker
before they are shown to the public (see docs/LANGUAGES.md).
"""

LANGUAGES = {"en": "English", "af": "Afrikaans", "zu": "isiZulu", "st": "Sesotho"}
REVIEWED = {"en": True, "af": True, "zu": False, "st": False}

PHRASES = {
    "en": {
        "your_business": "Your business",
        "score": "{name} scores {fit} on fit and {ready} on readiness for this opportunity.",
        "blocked": "The award is blocked until these are in place: {steps}.",
        "step": "{label} from {issuer} ({days} days, R{cost})",
        "once_ok": "Once they are, the business moves to the award-ready quadrant.",
        "once_low": "Fit remains below the 60 threshold even after remediation.",
        "none": "No readiness gaps are open.",
        "risk": "Capacity warning: the contract is {pct}% of annual turnover, and R{wc} of working capital is needed before first payment.",
        "not_eligible": "Not eligible",
    },
    "af": {
        "your_business": "U besigheid",
        "score": "{name} behaal {fit} vir pas en {ready} vir gereedheid vir hierdie geleentheid.",
        "blocked": "Die toekenning is geblokkeer totdat dit in plek is: {steps}.",
        "step": "{label} van {issuer} ({days} dae, R{cost})",
        "once_ok": "Sodra dit in plek is, skuif die besigheid na die toekenningsgereed-kwadrant.",
        "once_low": "Pas bly onder die drempel van 60, selfs ná regstelling.",
        "none": "Geen gereedheidsgapings is oop nie.",
        "risk": "Kapasiteitswaarskuwing: die kontrak is {pct}% van jaarlikse omset, en R{wc} bedryfskapitaal is nodig voor die eerste betaling.",
        "not_eligible": "Nie geskik nie",
    },
    "zu": {
        "your_business": "Ibhizinisi lakho",
        "score": "{name} linamaphuzu angu-{fit} ekufanelekeni namaphuzu angu-{ready} ekulungeleni leli thuba.",
        "blocked": "Umklomelo umiswe kuze kube lapho lokhu sekukhona: {steps}.",
        "step": "{label} evela ku-{issuer} (izinsuku ezingu-{days}, R{cost})",
        "once_ok": "Uma sekukhona, ibhizinisi liba ngelilungele ukuklonyeliswa.",
        "once_low": "Ukufaneleka kusaphansi komkhawulo ongu-60 ngisho nangemva kokulungisa.",
        "none": "Azikho izikhala zokulungela ezivulekile.",
        "risk": "Isixwayiso sekhono: inkontileka ingu-{pct}% wenzuzo yonyaka, futhi kudingeka u-R{wc} wemali yokusebenza ngaphambi kokukhokhelwa kokuqala.",
        "not_eligible": "Alifaneleki",
    },
    "st": {
        "your_business": "Khoebo ea hau",
        "score": "{name} e na le lintlha tse {fit} ho ho loketsa le tse {ready} ho boitokisetso bakeng sa monyetla ona.",
        "blocked": "Khetho e emisitsoe ho fihlela lintho tsena li le teng: {steps}.",
        "step": "{label} ho tsoa ho {issuer} (matsatsi a {days}, R{cost})",
        "once_ok": "Ha li se li le teng, khoebo e fetela karolong ea ba loketseng ho fuoa.",
        "once_low": "Ho loketsa ho lula ka tlase ho moeli oa 60 le ka mor'a ho lokisa.",
        "none": "Ha ho na likheo tsa boitokisetso tse bulehileng.",
        "risk": "Temoso ea bokhoni: konteraka ke {pct}% ea thekiso ea selemo, 'me ho hlokahala R{wc} ea chelete ea ts'ebetso pele ho tefo ea pele.",
        "not_eligible": "Ha e a tšoanela",
    },
}

CREDENTIALS = {
    "af": {
        "TCS": "Belastingnakomingstatus-PIN",
        "BBBEE": "B-BBEE-eedsverklaring",
        "COID": "Brief van goeie standing (COIDA)",
        "CSD": "CSD-registrasie",
        "CIDB": "CIDB-graderingsertifikaat",
    },
    "zu": {
        "TCS": "I-PIN yesimo sokuhambisana nentela",
        "BBBEE": "Isitatimende esifungelwe se-B-BBEE",
        "COID": "Incwadi yokuma kahle (COIDA)",
        "CSD": "Ukubhaliswa kwe-CSD",
        "CIDB": "Isitifiketi sezinga se-CIDB",
    },
    "st": {
        "TCS": "PIN ea boemo ba ho ikamahanya le lekhetho",
        "BBBEE": "Boitlamo bo hlapaneng ba B-BBEE",
        "COID": "Lengolo la boemo bo botle (COIDA)",
        "CSD": "Ngoliso ea CSD",
        "CIDB": "Setifikeiti sa mohato oa CIDB",
    },
}


def normalise(lang: str | None) -> str:
    return lang if lang in LANGUAGES else "en"


def rationale(name: str, facts: dict, lang: str = "en") -> str:
    """The plain-words explanation of a match, from fixed templates, in the chosen language."""
    lang = normalise(lang)
    p = PHRASES[lang]
    parts = [p["score"].format(name=name, fit=facts["fit_score"], ready=facts["readiness_score"])]
    gaps = facts["gaps"]
    if gaps:
        steps = "; ".join(
            p["step"].format(
                label=CREDENTIALS.get(lang, {}).get(g.get("credential", ""), g["label"]),
                issuer=g["issuer"],
                days=g["days"],
                cost=f"{g['cost_zar']:,}",
            )
            for g in gaps
        )
        parts.append(p["blocked"].format(steps=steps))
        parts.append(p["once_ok"] if facts["fit_score"] >= 60 else p["once_low"])
    else:
        parts.append(p["none"])
    r = facts["risk"]
    if r["overtrading"]:
        parts.append(p["risk"].format(pct=r["overtrading_pct"], wc=f"{r['working_capital_zar']:,}"))
    return " ".join(parts)
