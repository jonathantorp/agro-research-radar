# AGRO Research Radar – Netlify prototype

**Status:** Klar til upload til GitHub og kobling til Netlify, men **ikke deployet**. Den automatiske scraping fra AU Pure er **ikke live-valideret**; i det lokale miljø kunne AU Pure ikke nås. Projektet starter med ni verificerbare pilot-publikationsposter, ikke et komplet 3-månedersudtræk.

## Det skal du gøre én gang

1. Pak `AGRO_Research_Radar_Netlify_Klar.zip` ud.
2. Åbn dit tomme GitHub-repository: `https://github.com/jonathantorp/agro-research-radar`.
3. Vælg **Add file → Upload files**. Træk **indholdet af den udpakkede mappe** over, inklusive `.github`-mappen. GitHub understøtter upload af mapper. Vælg **Commit changes** på `main` (hvis GitHub opretter en ny branch, merge den til `main`). Kontrollér efter upload, at filen `.github/workflows/radar.yml` ligger korrekt. På Mac er `.github` en skjult mappe; tryk `Cmd+Shift+.` i Finder for at vise den.
4. Gå til `https://app.netlify.com/start` → **Import from Git** → GitHub → vælg `jonathantorp/agro-research-radar`. Sæt **branch: main**, **build command: `mkdir -p site && cp index.html publications.json sync.json site/`**, **publish directory: `site`** (Netlify vil også læse samme oplysninger fra `netlify.toml`). Vælg Deploy. Kontroller at sitet er offentligt, hvis kolleger uden login skal kunne åbne det. Notér din `*.netlify.app`-adresse.
5. Gå til GitHub → dit repo → **Actions → AGRO Research Radar - ugentlig opdatering → Run workflow**. Åbn loggen. Den bør køre tests, forsøge Pure-hentning og commite status/resultater. En fejl fra Pure skal fremgå som en advarsel i dashboardet, ikke skjules som en succesfuld scanning.
6. Under GitHub **Settings → Actions → General**, kontrollér workflowets `GITHUB_TOKEN`-rettigheder. Workflowet sætter selv `contents: write`; nogle repositoryindstillinger kan dog begrænse det. Hvis bot-commit afvises, justér rettigheder i henhold til GitHubs vejledning.
7. **For egentlige automatiske AI-ratings:** Efter AU-godkendelse af behandling af offentligt publikationindhold, opret en separat OpenAI API-nøgle. Tilføj den kun som GitHub **Settings → Secrets and variables → Actions → New repository secret** med navnet `OPENAI_API_KEY`. Ingen hemmelige nøgler må placeres i HTML eller ZIP. `gpt-6-luna` bruges som standard; eksterne API-kald afregnes særskilt. Uden nøgle kan scraperen indsamle metadata, men ratings fra koden forbliver *regelbaserede*, og dashboardet viser dette.

## Det sker derefter

GitHub Actions starter ca. hver **onsdag kl. 08:15 dansk vintertid / 09:15 sommertid** (07:15 UTC) og gennemgår offentligt tilgængelige Pure-sider for AGRO. Den analyserer evt. abstracts og supplerer med titel/forfattere, hvis abstract mangler. Der oprettes nye poster og ratings, og `publications.json` / `sync.json` committes på `main`. Netlify genudgiver siden automatisk, når GitHub modtager ændringer. URL'en er den samme.

De enkelte Pure-sider forsøges gennemgået, indtil sidernes år falder uden for perioden eller en sikkerhedsgrænse nås. Indsamlingen er best effort og kan være begrænset af Pure robots.txt, HTML-struktur, HTTP-afvisninger eller manglende udgivelsesdatoer. **Ingen kan på nuværende tidspunkt garantere fuld dækning.** Hvis adgang eller metadata mangler, skal dashboardet vise det tydeligt.

## Vigtigt

- Dette er en **offentlig prototype**. Gem kun åbne publikationer og offentlige metadata. Noter skrevet i dashboardet ligger kun lokalt i den enkelte medarbejders browser; de er ikke delt mellem kolleger.
- Selv med adgang til abstract er en AI-vurdering kun et redaktionelt forslag. Ingen publicering uden fagligt tjek hos forskeren.
- Vær opmærksom på, at et manuelt drag-and-drop-deploy i Netlify *alene* er statisk. For ugentlige opdateringer skal Netlify være **Git-forbundet**.
- Den tidligere oprettede **ChatGPT-onsdagsopgave** er en separat automatisering. Stop den først, når denne GitHub/Netlify-kæde har gennemført en korrekt ugentlig kørsel, hvis du ikke vil have dubletter.
- `publi­cations.json` skal ikke indeholde artikelabstracts i den offentlige version; `strip_abstracts.py` fjerner dem før commit. Kontrollér gerne payload og vilkår, før du anvender eksterne modelkald.

## Filer

- `index.html`: browser-dashboard med søgning, filtre, kildehenvisninger, ratings og lokale noter.
- `publications.json`: testede historiske pilot-poster og senere ugentligt indsamlede metadata.
- `sync.json`: status for sidste kørsel, dækning og fejl.
- `scrape_pure.py`: offentlig Pure-indhentning under robots- og adgangsbegrænsninger.
- `rate_ai.py`: vurdering via API, kun hvis en nøgle findes.
- `strip_abstracts.py`: fjerner abstracts fra offentlig JSON.
- `.github/workflows/radar.yml`: planlagt ugentlig indsamling og Git-commit.
- `netlify.toml`: konfigureret build til Netlify.
- `tests/`: lokale enhedstests.

**Lokale tests:** `python -m pip install -r requirements.txt` og `python -m unittest discover -s tests -v`.
