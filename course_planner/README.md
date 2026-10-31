# Kurs planlayıcısı (gün 18, CrewAI)

Müəllim mövzunu və dərs sayını verir, üç agentli komanda kursun planını qurur,
müəllim baxır və bir əmrlə dərsləri sinfin cədvəlinə yazır.

```
Kurikulum dizayneri → Metodist → Qiymətləndirmə mütəxəssisi → plan.json + plan.md
   (dərs ardıcıllığı)  (məqsəd, fəaliyyət)  (ev tapşırığı, quiz, JSON)
```

- Proses ardıcıldır, hər agent əvvəlkilərin nəticəsini görür (`context`).
- LLM MasterAI-nin öz fallback zənciridir (`MasterAILLM` → `complete_with_fallback`:
  vLLM → Groq → Claude), CrewAI-nın litellm-i yox: eyni açarlar, ayrıca konfiqurasiya yoxdur.
- CrewAI telemetriyası söndürülür (planda kursun mövzusu var).
- CrewAI ~1 GB asılılıqdır, ona görə **serverə qoyulmur**: planlayıcı müəllimin
  kompüterində işləyir və dərsləri mövcud REST API ilə müəllimin tokeni ilə yazır
  (gün 11-in MCP serveri kimi). Serverdə yeni icazə yolu yoxdur.

## İşlətmək

```bash
pip install -r requirements-agents.txt
export GROQ_API_KEY=...                      # və ya .env
python -m course_planner.cli plan --topic "Azərbaycan Konstitusiyası" --lessons 8 --out plan.json
# plan.md-ni oxu; lazım olsa plan.json-u düzəlt
export MASTERAI_EMAIL=... MASTERAI_PASSWORD=...
python -m course_planner.cli push plan.json --class-id 3 --start 2026-11-10 --weekdays 1,3 --time 18:00
```

Sinfin ID-si: `dersler.html`-də və ya MCP-də `list_classes`. Həftə günləri 1 = bazar
ertəsi ... 7 = bazar, saat Bakı vaxtıdır. Planlama və yazma qəsdən ayrıdır: müəllim
AI-nın planını görmədən dərslər sinfin cədvəlinə düşməməlidir.
