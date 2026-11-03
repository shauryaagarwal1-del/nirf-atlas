# NIRF source map (Phase 1: source reconnaissance)

What the official site https://www.nirfindia.org offers for 2017–2025, where every piece sits in the HTML, and
what is missing. Checked on **3 November 2026** with:

```bash
python -m scraper.explore_source --markdown
```

- **300 HTML pages** downloaded once and cached in `data/raw/html/<year>/` (27 MB, gitignored).
  Re-running the script reads the cache and makes **no** new requests.
- Machine-readable findings (every table, header, row count and format count): `data/raw/source_inventory.json`.
- Every request returned HTTP 200. Nothing was blocked: no login, no CAPTCHA, no JavaScript-only content.

---

## 1. How the site is laid out

| Level | URL pattern | Notes |
|---|---|---|
| Home | `https://www.nirfindia.org/` | Links one index page per year, 2016–2025 (2016 is outside our scope). |
| Year index | 2017–2020: `Rankings/<YEAR>/Ranking<YEAR>.html`<br>2021–2025: `Rankings/<YEAR>/Ranking.html` | Lists the categories published that year, plus the yearly report PDF. |
| Category page | `Rankings/<YEAR>/<Stem>Ranking.html` | Stems: `Overall, University, College, Research, Engineering, Management, Pharmacy, Medical, Dental, Law, Architecture, Agriculture, Innovation, OPENUNIVERSITY, SKILLUNIVERSITY, STATEPUBLICUNIVERSITY, SDGInstitutions`. |
| Rank-band page | `Rankings/<YEAR>/<Stem>Ranking150.html`, `…200.html`, `…300.html`, `…100.html`, `…50.html` | **The number in the file name is NOT the band.** E.g. 2020 `EngineeringRanking150.html` holds band 201–250. The band is in the link text ("Rank-band: 201-250") and the page heading. |
| Participant list | `Rankings/<YEAR>/<Stem>RankingALL.html` (2017: `…RankingAll.html`) | "List of Participating Institutions". 2024 Skill University links to a misspelt `SKILLUNIVERSTIYRankingAll.html`, which still works. |
| Per-institution files | `nirfpdfcdn/<YEAR>/pdf/<Category>/<ID>.pdf` and `nirfpdfcdn/<YEAR>/graph/<Category>/<ID>.jpg` | The data each institution submitted, and a score graph. Linked from every ranked row (not Research). **Not downloaded.** |
| Yearly report | `nirfpdfcdn/<YEAR>/pdf/Report/IR<YEAR>_Report.pdf` (2017: `nirfpdfcdn/2017/IR2017_Report.pdf`, 2018: `nirfpdfcdn/2018/pdf/nirf_2018_final.pdf`) | **Not downloaded** (backup only, see Gaps). |

The hint "2017 pages sit at `nirfindia.org/<Category>Ranking.html`" is **wrong**: that URL returns 404. 2017 uses the
same `Rankings/2017/<Category>Ranking.html` pattern as every other year.

---

## 2. Year × category table

`✓ N + M` = N institutions with an exact rank and score on the main page **+** M institutions listed only inside rank
bands (name, city, state). `✗` = the category was not published that year. Each tick links to the main page.

| Category | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| Overall | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2017/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2018/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2019/OverallRanking.html) | [✓ 101 + 99](https://www.nirfindia.org/Rankings/2020/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2021/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2022/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2023/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2024/OverallRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2025/OverallRanking.html) |
| Engineering | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2017/EngineeringRanking.html) | [✓ 100 + 101](https://www.nirfindia.org/Rankings/2018/EngineeringRanking.html) | [✓ 200](https://www.nirfindia.org/Rankings/2019/EngineeringRanking.html) | [✓ 200 + 100](https://www.nirfindia.org/Rankings/2020/EngineeringRanking.html) | [✓ 200 + 100](https://www.nirfindia.org/Rankings/2021/EngineeringRanking.html) | [✓ 200 + 100](https://www.nirfindia.org/Rankings/2022/EngineeringRanking.html) | [✓ 100 + 101](https://www.nirfindia.org/Rankings/2023/EngineeringRanking.html) | [✓ 100 + 200](https://www.nirfindia.org/Rankings/2024/EngineeringRanking.html) | [✓ 100 + 200](https://www.nirfindia.org/Rankings/2025/EngineeringRanking.html) |
| Management | [✓ 50 + 50](https://www.nirfindia.org/Rankings/2017/ManagementRanking.html) | [✓ 50 + 50](https://www.nirfindia.org/Rankings/2018/ManagementRanking.html) | [✓ 75 + 25](https://www.nirfindia.org/Rankings/2019/ManagementRanking.html) | [✓ 75 + 25](https://www.nirfindia.org/Rankings/2020/ManagementRanking.html) | [✓ 75 + 25](https://www.nirfindia.org/Rankings/2021/ManagementRanking.html) | [✓ 101 + 24](https://www.nirfindia.org/Rankings/2022/ManagementRanking.html) | [✓ 100 + 25](https://www.nirfindia.org/Rankings/2023/ManagementRanking.html) | [✓ 100 + 25](https://www.nirfindia.org/Rankings/2024/ManagementRanking.html) | [✓ 100 + 25](https://www.nirfindia.org/Rankings/2025/ManagementRanking.html) |
| University | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2017/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2018/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2019/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2020/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2021/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2022/UniversityRanking.html) | [✓ 100 + 101](https://www.nirfindia.org/Rankings/2023/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2024/UniversityRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2025/UniversityRanking.html) |
| College | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2017/CollegeRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2018/CollegeRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2019/CollegeRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2020/CollegeRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2021/CollegeRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2022/CollegeRanking.html) | [✓ 100 + 100](https://www.nirfindia.org/Rankings/2023/CollegeRanking.html) | [✓ 100 + 200](https://www.nirfindia.org/Rankings/2024/CollegeRanking.html) | [✓ 100 + 200](https://www.nirfindia.org/Rankings/2025/CollegeRanking.html) |
| Pharmacy | [✓ 50 + 50](https://www.nirfindia.org/Rankings/2017/PharmacyRanking.html) | [✓ 50 + 50](https://www.nirfindia.org/Rankings/2018/PharmacyRanking.html) | [✓ 75 + 25](https://www.nirfindia.org/Rankings/2019/PharmacyRanking.html) | [✓ 75 + 26](https://www.nirfindia.org/Rankings/2020/PharmacyRanking.html) | [✓ 75 + 25](https://www.nirfindia.org/Rankings/2021/PharmacyRanking.html) | [✓ 101 + 24](https://www.nirfindia.org/Rankings/2022/PharmacyRanking.html) | [✓ 100 + 25](https://www.nirfindia.org/Rankings/2023/PharmacyRanking.html) | [✓ 100 + 25](https://www.nirfindia.org/Rankings/2024/PharmacyRanking.html) | [✓ 101 + 24](https://www.nirfindia.org/Rankings/2025/PharmacyRanking.html) |
| Medical | ✗ | [✓ 25](https://www.nirfindia.org/Rankings/2018/MedicalRanking.html) | [✓ 30](https://www.nirfindia.org/Rankings/2019/MedicalRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2020/MedicalRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2021/MedicalRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2022/MedicalRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2023/MedicalRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2024/MedicalRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2025/MedicalRanking.html) |
| Architecture and Planning | ✗ | [✓ 10](https://www.nirfindia.org/Rankings/2018/ArchitectureRanking.html) | [✓ 15](https://www.nirfindia.org/Rankings/2019/ArchitectureRanking.html) | [✓ 20](https://www.nirfindia.org/Rankings/2020/ArchitectureRanking.html) | [✓ 25](https://www.nirfindia.org/Rankings/2021/ArchitectureRanking.html) | [✓ 30](https://www.nirfindia.org/Rankings/2022/ArchitectureRanking.html) | [✓ 30](https://www.nirfindia.org/Rankings/2023/ArchitectureRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2024/ArchitectureRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2025/ArchitectureRanking.html) |
| Law | ✗ | [✓ 10](https://www.nirfindia.org/Rankings/2018/LawRanking.html) | [✓ 15](https://www.nirfindia.org/Rankings/2019/LawRanking.html) | [✓ 20](https://www.nirfindia.org/Rankings/2020/LawRanking.html) | [✓ 30](https://www.nirfindia.org/Rankings/2021/LawRanking.html) | [✓ 30](https://www.nirfindia.org/Rankings/2022/LawRanking.html) | [✓ 30](https://www.nirfindia.org/Rankings/2023/LawRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2024/LawRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2025/LawRanking.html) |
| Special Mention (2018, unranked, see below) | ✗ | [✓ 4](https://www.nirfindia.org/Rankings/2018/SpecialRank.html) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Dental | ✗ | ✗ | ✗ | [✓ 30](https://www.nirfindia.org/Rankings/2020/DentalRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2021/DentalRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2022/DentalRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2023/DentalRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2024/DentalRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2025/DentalRanking.html) |
| Research Institutions | ✗ | ✗ | ✗ | ✗ | [✓ 50](https://www.nirfindia.org/Rankings/2021/ResearchRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2022/ResearchRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2023/ResearchRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2024/ResearchRanking.html) | [✓ 50](https://www.nirfindia.org/Rankings/2025/ResearchRanking.html) |
| Agriculture and Allied Sectors | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | [✓ 40](https://www.nirfindia.org/Rankings/2023/AgricultureRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2024/AgricultureRanking.html) | [✓ 40](https://www.nirfindia.org/Rankings/2025/AgricultureRanking.html) |
| Innovation | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | [✓ 10](https://www.nirfindia.org/Rankings/2023/InnovationRanking.html) | [✓ 10 + 40](https://www.nirfindia.org/Rankings/2024/InnovationRanking.html) | [✓ 10 + 40](https://www.nirfindia.org/Rankings/2025/InnovationRanking.html) |
| Open University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | [✓ 3](https://www.nirfindia.org/Rankings/2024/OPENUNIVERSITYRanking.html) | [✓ 3](https://www.nirfindia.org/Rankings/2025/OPENUNIVERSITYRanking.html) |
| Skill University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | [✓ 3](https://www.nirfindia.org/Rankings/2024/SKILLUNIVERSITYRanking.html) | [✓ 3](https://www.nirfindia.org/Rankings/2025/SKILLUNIVERSITYRanking.html) |
| State Public University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | [✓ 50 + 50](https://www.nirfindia.org/Rankings/2024/STATEPUBLICUNIVERSITYRanking.html) | [✓ 50 + 50](https://www.nirfindia.org/Rankings/2025/STATEPUBLICUNIVERSITYRanking.html) |
| SDG Institutions | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | [✓ 10 + 41](https://www.nirfindia.org/Rankings/2025/SDGInstitutionsRanking.html) |

The 2018 "Special Mention" page lists 4 institutions in alphabetical order, with no rank and no score (ICAR–National
Dairy Research Institute, Indian Agricultural Research Institute, JNCASR, TIFR). It is not a ranking.

### Exact ranks and bands per category-year

| Category | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| Overall | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100 (101 rows, tie)<br>102-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 |
| Engineering | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–200 | 1–200<br>201-250<br>251-300 | 1–200<br>201-250<br>251-300 | 1–200<br>201-250<br>251-300 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200<br>201-300 | 1–100<br>101-150<br>151-200<br>201-300 |
| Management | 1–50<br>51-75<br>76-100 | 1–50<br>51-75<br>76-100 | 1–75<br>76-100 | 1–75<br>76-100 | 1–75<br>76-100 | 1–100 (101 rows, tie)<br>102-125 | 1–100<br>101-125 | 1–100<br>101-125 | 1–100<br>101-125 |
| University | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 |
| College | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200 | 1–100<br>101-150<br>151-200<br>201-300 | 1–100<br>101-150<br>151-200<br>201-300 |
| Pharmacy | 1–50<br>51-75<br>76-100 | 1–50<br>51-75<br>76-100 | 1–75<br>76-100 | 1–75<br>76-100 | 1–75<br>76-100 | 1–100 (101 rows, tie)<br>102-125 | 1–100<br>101-125 | 1–100<br>101-125 | 1–100 (101 rows, tie)<br>102-125 |
| Medical | ✗ | 1–25 | 1–30 | 1–40 | 1–50 | 1–50 | 1–50 | 1–50 | 1–50 |
| Architecture and Planning | ✗ | 1–10 | 1–15 | 1–20 | 1–25 | 1–30 | 1–30 | 1–40 | 1–40 |
| Law | ✗ | 1–10 | 1–15 | 1–20 | 1–30 | 1–30 | 1–30 | 1–40 | 1–40 |
| Dental | ✗ | ✗ | ✗ | 1–30 | 1–40 | 1–40 | 1–40 | 1–40 | 1–40 |
| Research Institutions | ✗ | ✗ | ✗ | ✗ | 1–50 | 1–50 | 1–50 | 1–50 | 1–50 |
| Agriculture and Allied Sectors | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1–40 | 1–40 | 1–40 |
| Innovation | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1–10 | 1–10<br>11-50 | 1–10<br>11-50 |
| Open University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1–3 | 1–3 |
| Skill University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1–3 | 1–3 |
| State Public University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1–50<br>51-100 | 1–50<br>51-100 |
| SDG Institutions | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1–10<br>11-50 |

The cut-off between exact ranks and bands **moves over time** (Engineering: exact to 100, then to 200 in 2019–2022,
then back to 100). For band-transition questions the bands must be defined per category-year, not hard-coded.

### Participating institutions per category-year

From the "List of Participating Institutions" pages (`–` = no such list is linked).

| Category | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| Overall | 724 | 957 | 1479 | 1667 | 1657 | 1875 | 2478 | 2781 | 4045 |
| Engineering | 1007 | 906 | 969 | 1071 | 1143 | 1249 | 1314 | 1463 | 1584 |
| Management | 542 | 487 | 555 | 630 | 659 | 751 | 776 | 876 | 1026 |
| University | – | – | – | – | – | – | – | – | – |
| College | 535 | 1087 | 1304 | 1659 | 1802 | 2270 | 2746 | 3371 | 4030 |
| Pharmacy | 316 | 286 | 301 | 334 | 351 | 400 | 435 | 467 | 594 |
| Medical | ✗ | 101 | 113 | 118 | 111 | 151 | 176 | 182 | 223 |
| Architecture and Planning | ✗ | 59 | 65 | 66 | 78 | 91 | 105 | 115 | 131 |
| Law | ✗ | 71 | 80 | 97 | 120 | 147 | 162 | 195 | 267 |
| Dental | ✗ | ✗ | ✗ | 115 | 117 | 142 | 155 | 184 | 223 |
| Research Institutions | ✗ | ✗ | ✗ | ✗ | – | – | – | – | – |
| Agriculture and Allied Sectors | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 152 | 145 | 173 |
| Innovation | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | – | 808 | 777 |
| Open University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 12 | 15 |
| Skill University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 4 | 11 |
| State Public University | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 168 | – |
| SDG Institutions | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 791 |

---

## 3. How the data is embedded in the HTML

### Main ranking table (every category page)
`<table id="tbl_overall">` (the id is `tbl_overall` on **every** category page, not only Overall). Columns:

```
Institute ID | Name | City | State | Score | Rank
```

Exceptions: Innovation 2023 = `Institute ID | Name | State | Band`; Innovation 2024–25, Open University, Skill
University, SDG Institutions = `Institute ID | Name | City | State | Rank` (no score).

### The five parameter scores: hidden nested table
Inside the **Name** cell of every ranked row there is a hidden block, opened on the site by "More Details":

```html
<td>
  Indian Institute of Technology Madras
  <div style="float:right;"> More Details | <a href=".../pdf/Overall/IR-O-U-0456.pdf"> | <a href=".../graph/...jpg"> </div>
  <div class="tbl_hidden" style="display:none;">
    <table><thead><tr><th>TLR (100)</th><th>RPC (100)</th><th>GO (100)</th><th>OI (100)</th><th>PERCEPTION (100)</th></tr></thead>
           <tbody><tr><td>90.58</td><td>88.02</td><td>87.01</td><td>63.34</td><td>100.00</td></tr></tbody></table>
  </div>
</td>
```

So the parser must (a) take the Name cell's own text **without** the nested `div`s, and (b) read the five numbers from
the nested table. This layout is the same in **all years 2017–2025** for every scored category.

- **Research Institutions (2021–2025) use different parameters:** `QNR (100) | QLR (100) | SFC (100) | OI (100) |
  PERCEPTION (100)`. The page gives no expansion of QNR/QLR/SFC; their meaning must be taken from the NIRF Research
  methodology before we label them. They must not be put in the same column as TLR/RPC/GO.
- **No parameter scores** for Innovation, Open University, Skill University and SDG Institutions (rank only).

### Parameter-wise tabs ("By TLR / By RPC …")
Five extra tables `tbl_tlr, tbl_rpc, tbl_go, tbl_oi, tbl_pr` with columns
`Institute ID | Name | City | State | <P> Score | <P> Rank | Score | Rank`.
They exist on **every** category page in 2017 and 2018, and on the **University** page in every year 2019–2025.
They repeat the same institutions as the main table, but add a **rank on each parameter**. Values above 100 appear
(e.g. 2018 College, a GO rank of 492), so this looks like the rank among all evaluated institutions; to be confirmed
before we use it.

### Rank-band pages and participant lists
A single table with only `Name | City | State`, in alphabetical order: **no Institute ID, no score, no parameters, no
exact rank**. Band pages are headed e.g. "India Rankings 2025: Engineering (Rank-band: 101-150)". Participant lists
use `<table id="tblAllInstitutes">`.

### Rank formats seen
| Format | Where |
|---|---|
| Plain integer | Everywhere (the normal case). |
| Ties: same integer repeated, next rank skipped | E.g. 2020 Overall two at 100 (101 rows; band then starts at 102), 2022 Management/Pharmacy, 2025 Pharmacy, 2019 Engineering 198→200, Innovation 2023 two at 8. Band pages can hold 49 or 51 names for the same reason. |
| Band text `101-150` | Only via rank-band pages (taken from link text / heading), never inside a main table. |
| `21A`, `26A` | 2018 Engineering. |
| `16A` | 2018 Pharmacy. |
| `Rank Withdrawn` | 2018 College (Bishop Heber College; score 67.63 still shown, placed after rank 2). |
| `Rank Withdrawn*` merged over Score+Rank | 2025 Dental (Faculty of Dental Sciences, IMS BHU). The row has a hidden `display:none` cell holding 18 and no parameters. Footnote: BHU and the Faculty submitted data independently with different placement data. |

The "A" ranks are not explained on the page. Each one has a **higher** score than the institution at the plain rank
(21A = 53.24 vs rank 21 = 53.16), so they look like late insertions without renumbering. **Decision needed**: how to
store them (suggestion: keep the original text in `rank_raw`, put a numeric `rank` only after we confirm the meaning
in the 2018 report).

### Institute ID formats
| Years | Example (IIT Madras, Overall) | Pattern |
|---|---|---|
| 2017 | `IR17-I-1-1-77`, `IR17-ENGG-…`, `IR17-MGMT-…` | Year-specific and category-specific. Not linkable to later IDs. |
| 2018 | `IR-2-O-OE-U-0456` | `IR-<n>-<category>-<group>-<type>-<code>` |
| 2019–2025 | `IR-O-U-0456` | `IR-<category letter>-<type letter>-<code>` |
| Innovation 2023 | `ARI-U-0456` | Old ARIIA scheme. |

From 2018 on, the trailing `<type>-<code>` (`U-0456`) stays the same for an institution across years **and**
categories (IIT Madras is `…-U-0456` in 2018 and in every year 2019–2025). This is our best join key from 2018.
2017 has to be linked by name (+ city/state). Category letters seen: O Overall/University/State Public, C College,
E Engineering, M Management, P Pharmacy, D Medical, N Dental, L Law, A Architecture, R Research, G Agriculture,
I Innovation, V Open University, S Skill University, B SDG.

---

## 4. Parsing notes per year

| Year | Index page | Categories | What is different |
|---|---|---|---|
| **2017** | `Ranking2017.html` | 6: Overall, Engineering, Management, University, College, Pharmacy | 2017-only ID scheme (link by name). Parameter-wise tabs on every page. Management/Pharmacy exact 1–50, bands 51–75, 76–100. Participant link spelt `…RankingAll.html`. |
| **2018** | `Ranking2018.html` | 9 (+ Medical, Architecture, Law) + "Special Mention" page | 2018-only ID scheme (code part matches later years). Ranks `21A`, `26A`, `16A`, `Rank Withdrawn`. Parameter-wise tabs on every page. |
| **2019** | `Ranking2019.html` | 9 | ID scheme `IR-O-U-0456` begins (stable to 2025). Engineering exact 1–200, no bands. Parameter-wise tabs only on University. |
| **2020** | `Ranking2020.html` | 10 (+ Dental) | Overall tie at 100 → band "102-150". Engineering 1–200 + 201–250, 251–300. |
| **2021** | `Ranking.html` (new name) | 11 (+ Research) | Research: QNR/QLR/SFC parameters, no PDF links, no participant list. |
| **2022** | `Ranking.html` | 11 | Management and Pharmacy tie at 100 → band "102-125". |
| **2023** | `Ranking.html` | 13 (+ Agriculture, Innovation) | Engineering back to exact 1–100. Innovation page in the old ARIIA format: `ARI-` IDs, names and states in UPPER CASE, no City, rank column called "Band" (holds 1–10), no score, no bands. |
| **2024** | `Ranking.html` | 16 (+ Open University, Skill University, State Public University) | Innovation switches to normal `IR-I-` IDs with City and band 11–50. Open/Skill: top 3, rank only. State Public University reuses Overall-style `IR-O-` IDs, band 51–100. College and Engineering add band 201–300. |
| **2025** | `Ranking.html` | 17 (+ SDG Institutions) | SDG: rank only, band 11–50. Dental "Rank Withdrawn*" row with footnote. State Public University has no participant list link. |

General notes for the pipeline:
- Read the raw **bytes** and let BeautifulSoup detect the encoding (the footer contains non-UTF-8 characters).
- Some pages keep old rows inside HTML comments (`<!-- <tr>… -->`). The parser ignores comments, which is what we want.
- Names and states are not consistent: e.g. "Indian Institute of Science" vs "Indian Institute of Science, Bengaluru"
  (2024), and UPPER CASE in Innovation 2023. These need the alias tables in `data/mappings/`.
- Scores have 2 decimals. Ties and withdrawn rows mean "row count" ≠ "last rank".

---

## 5. Gaps (and suggested backups, not used)

| # | Gap | Impact | Suggested backup (only with your OK) |
|---|---|---|---|
| 1 | Banded institutions (e.g. Overall 101–200) have **no score, no parameters, no ID and no exact rank** on the site. | Band transitions work; score and parameter analysis is limited to the exact-rank lists. | Yearly India Rankings report PDFs (URLs in §1). We have not checked whether they hold scores for banded institutions. |
| 2 | 2017 IDs cannot be joined to 2018+ IDs. | 2017 must be linked by name + city + state. | None needed: fuzzy name matching plus a hand-checked alias table. |
| 3 | Meaning of `21A` / `26A` / `16A` (2018) is not stated anywhere on the pages. | Small (3 rows), but the rank value must not be guessed. | 2018 report PDF `nirfpdfcdn/2018/pdf/nirf_2018_final.pdf`. |
| 4 | Research uses QNR/QLR/SFC instead of TLR/RPC/GO; the page does not expand these abbreviations. | Research cannot share parameter charts with other categories. | NIRF methodology document for Research Institutions on nirfindia.org. |
| 5 | Innovation, Open University, Skill University, SDG: rank only, no score. | These categories can only appear in rank-based charts. | None on the site. |
| 6 | Innovation before 2023 was not a NIRF category. The 2023 page still uses ARIIA IDs, so earlier innovation rankings were published separately (ARIIA). We did not check that site. | No Innovation trend before 2023. | ARIIA results, a separate ranking, only if you want it. |
| 7 | University and Research have no participant list. | Participation counts are missing for these two. | Report PDFs. |
| 8 | 2016 exists on the site but is outside the 2017–2025 scope. | None. | — |

Nothing was blocked or missing on the server side: every linked page downloaded on the first try.
Third-party mirrors (e.g. Kaggle datasets of NIRF tables) exist but were **not** used and will not be used without your approval.
