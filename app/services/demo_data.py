DEMO_COMPANIES = [
    {
        "ogrn": "1137847232852",
        "inn": "7811554010",
        "name_full": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"УМНОЕ ПРОСТРАНСТВО\"",
        "name_short": "Умное пространство",
        "brand": "ecom.tech",
        "status": "ACTIVE",
        "reg_date": "2013-06-19",
        "flags": ["mass_layoffs_2024_2025"],
    },
    {
        "ogrn": "1067746302491",
        "inn": "7701615630",
        "name_full": "АКЦИОНЕРНОЕ ОБЩЕСТВО \"МР ГРУПП\"",
        "name_short": "МР ГРУПП",
        "brand": "MR Group",
        "status": "ACTIVE",
        "reg_date": "2006-02-09",
        "flags": ["closed_ownership"],
    },
    {
        "ogrn": "1187746465037",
        "inn": "7707412852",
        "name_full": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"АСГАРД\"",
        "name_short": "АСГАРД",
        "brand": "ASGARD",
        "status": "BANKRUPT",
        "reg_date": "2018-05-16",
        "flags": ["bankrupt_2024"],
    },
    {
        "ogrn": "1027700000355",
        "inn": "7707083893",
        "name_full": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"СБЕРБАНК\"",
        "name_short": "Сбербанк",
        "brand": "Sberbank",
        "status": "ACTIVE",
        "reg_date": "2002-09-24",
        "flags": ["large_holding"],
    },
]


def find_demo_company(query: str):
    q = query.strip().lower()
    for c in DEMO_COMPANIES:
        if q in (c["ogrn"].lower(), c["inn"].lower()):
            return c
        if q in c["name_full"].lower() or q in c["name_short"].lower():
            return c
        if q in c.get("brand", "").lower():
            return c
    return None
