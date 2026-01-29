RISK_WEIGHTS = {
    "legal": "Критический",
    "financial": "Высокий",
    "reputation": "Средний",
    "operational": "Средний",
    "structural": "Умеренный",
}


def calculate_risks(company: dict, bankruptcy: dict, news_items: list):
    risks = []

    status = (company.get("status") or "").lower()
    if "ликвид" in status or "банкрот" in status:
        risks.append({
            "category": "Юридический",
            "weight": RISK_WEIGHTS["legal"],
            "reason": f"Статус компании: {company.get('status')}",
            "source": "ФНС",
        })

    if bankruptcy.get("found"):
        risks.append({
            "category": "Юридический",
            "weight": RISK_WEIGHTS["legal"],
            "reason": "Найдены признаки банкротства в ЕФРСБ",
            "source": "ЕФРСБ",
        })

    negative_news = [n for n in news_items if n.get("negative")]
    if negative_news:
        risks.append({
            "category": "Репутационный",
            "weight": RISK_WEIGHTS["reputation"],
            "reason": f"Негативные упоминания в новостях: {len(negative_news)}",
            "source": "Новости",
        })

    if not risks:
        risks.append({
            "category": "Низкий риск",
            "weight": "Низкий",
            "reason": "Критических факторов не обнаружено по доступным источникам",
            "source": "Сводный",
        })

    return risks
