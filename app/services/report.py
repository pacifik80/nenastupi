from datetime import datetime


def build_report(company: dict, risks: list, news_items: list) -> str:
    lines = []
    lines.append(f"Отчёт сформирован: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Компания: {company.get('name_full')} (ОГРН {company.get('ogrn')})")
    if company.get("status"):
        lines.append(f"Статус: {company.get('status')}")

    lines.append("\nКлючевые риски:")
    for r in risks[:5]:
        lines.append(f"- {r['category']} ({r['weight']}): {r['reason']} [{r['source']}]")

    lines.append("\nНовости (последние 90 дней):")
    if news_items:
        for n in news_items[:5]:
            lines.append(f"- {n.get('title')} ({n.get('link')})")
    else:
        lines.append("- Нет найденных упоминаний")

    lines.append("\nРекомендации:")
    lines.append("- Сверить реквизиты компании в ЕГРЮЛ перед подписанием договора")
    lines.append("- Запросить у работодателя копии уставных документов и сведения о руководителе")

    return "\n".join(lines)
