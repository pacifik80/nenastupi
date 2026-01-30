from datetime import datetime


def build_report(company: dict, risks: list, news_items: list, source_summary: dict | None = None) -> str:
    lines = []
    lines.append(f"Отчет сформирован: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Компания: {company.get('name_full')} (ОГРН {company.get('ogrn')})")
    if company.get("status"):
        lines.append(f"Статус: {company.get('status')}")

    if source_summary:
        lines.append("")
        lines.append("Источники:")
        ok = []
        failed = []
        details = []
        for name, meta in source_summary.items():
            if isinstance(meta, dict) and meta.get("ok") is False:
                failed.append(name)
                if meta.get("error"):
                    details.append(f"{name}: {meta.get('error')}")
            else:
                ok.append(name)
                if isinstance(meta, dict) and meta.get("meta"):
                    details.append(f"{name}: {meta.get('meta')}")
                elif isinstance(meta, dict) and meta.get("count") is not None:
                    details.append(f"{name}: count={meta.get('count')}")
        if ok:
            lines.append("- Успешно: " + ", ".join(ok))
        if failed:
            lines.append("- Не удалось: " + ", ".join(failed))
        if details:
            lines.append("- Детали: " + "; ".join(details))

    lines.append("\nКлючевые риски:")
    for r in risks[:5]:
        lines.append(f"- {r['category']} ({r['weight']}): {r['reason']} [{r['source']}]")

    lines.append("\nНовости (последние 90 дней):")
    if news_items:
        from app.services.sources.news import NewsClient

        for n in news_items[:5]:
            date_str = NewsClient.format_date(n.get("published"))
            source = n.get("source") or "Источник"
            link = n.get("link") or ""
            title = n.get("title") or ""
            reason = n.get("reason") or (title.split(" - ")[0] if title else "")
            if link:
                lines.append(f"- [{date_str}] - <a href=\"{link}\">{source}</a>")
            else:
                lines.append(f"- [{date_str}] - {source}")
            if title:
                lines.append(f"  {title}")
            if reason:
                lines.append(f"  {reason}")
    else:
        lines.append("- Нет найденных упоминаний")

    lines.append("\nРекомендации:")
    lines.append("- Сверить реквизиты компании в ЕГРЮЛ перед подписанием договора")
    lines.append("- Запросить у работодателя копии уставных документов и сведения о руководителе")

    return "\n".join(lines)
