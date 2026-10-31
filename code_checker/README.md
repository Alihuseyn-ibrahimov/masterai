# Kod yoxlayıcısı (gün 19): Docker sandbox + AutoGen

Proqramlaşdırma dərsində (məs. 5-ci ayın Python/PyTorch mövzuları) müəllim
tapşırıq verir, tələbələr `.py` faylı göndərir. Bu alət hər faylı **izolə
olunmuş Docker konteynerində** testlərlə yoxlayır, sonra iki AutoGen agenti
tələbəyə **həlli verməyən** rəy yazır.

Server tərəfinə toxunmur: Docker olan kompüterdə (müəllimin noutbuku) işləyir.

## Quraşdırma

```bash
python -m venv .venv-autogen
.venv-autogen/bin/pip install -r requirements-autogen.txt
docker pull python:3.12-slim
```

AutoGen CrewAI ilə **bir venv-ə qoyulmur**: `autogen-core` protobuf 5 bərkidir,
CrewAI-nın paketləri 6 ilə yığılıb, nəticədə CrewAI idxalı `VersionError` verir.

## İstifadə

```bash
python -m code_checker.cli list
python -m code_checker.cli check --exercise cut_ededlerin_cemi --file telebe.py --no-ai
python -m code_checker.cli check --exercise cut_ededlerin_cemi --file telebe.py     # + AI rəyi
python -m code_checker.cli batch --exercise soz_tezliyi --dir cavablar/ --out qiymetler.csv [--ai]
```

AI rəyi üçün `.env`: `GROQ_API_KEY` (Groq-un OpenAI-uyğun API-si) və ya
`VLLM_BASE_URL` + `VLLM_MODEL` (gün 17-nin öz modelimiz).

Yeni tapşırıq: `exercises/<id>.json` (`function`, `prompt`, `tests[]`: `call` +
`expected` Python literalı kimi).

## Təhlükəsizlik: niyə belə qurulub

Tələbə kodu etibarsızdır. Konteyner:
`--network none`, `--read-only` (yalnız 16 MB `/tmp`), 256 MB yaddaş, 0.5 CPU,
64 proses, `nobody` istifadəçisi, `--cap-drop ALL`, `no-new-privileges`,
kod qovluğu yalnız oxunur; vaxt keçəndə konteyner `docker kill` olunur.

**Qiymət saxtalaşdırıla bilmir.** İlk variantda testlər tələbə kodu ilə EYNİ
prosesdə işləyirdi: kod `print('{"passed": 5}')` + `os._exit(0)` ilə 5/5 ala
bilərdi. İndi grader testləri `stdin`-dən oxuyur (fayl kimi diskdə yoxdur) və
hər testi tələbə kodu ilə AYRI uşaq prosesdə çağırır; nəticəni grader özü
müqayisə edir. Sonsuz dövr/yaddaş partlaması yalnız həmin testi «vaxt bitdi» /
«yaddaş» edir, qalan testlər davam edir.

## Agentlər (AutoGen AgentChat 0.7)

`RoundRobinGroupChat`:
1. **yoxlayıcı** - test nəticəsini oxuyur, şübhəli yeri yoxlamaq üçün
   `run_experiment` alətini (eyni sandbox) çağırır, səbəbi tapır (≤3 alət addımı).
2. **mentor** - tələbəyə Azərbaycan dilində rəy yazır, həll kodu VERMİR,
   sonda `YEKUN` yazır (dayanma şərti; ehtiyat: 10 mesaj).

Mentorun cavabından 3 sətirdən uzun kod blokları `strip_solution` ilə
silinir: model təlimatı pozsa belə, tələbə hazır həlli görmür. Bal HƏMİŞƏ
testlərdəndir, agent balı dəyişmir.

## Testlər

`tests/test_code_checker.py`: sandbox məhdudiyyətləri (şəbəkə, yazma, vaxt,
yaddaş), saxta nəticə cəhdi, CLI, və AutoGen komandası
`ReplayChatCompletionClient` ilə (LLM-siz). Docker yoxdursa sandbox testləri,
AutoGen yoxdursa agent testləri keçilir; CI-da Docker var.
