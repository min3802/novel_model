# Live Guide Model Test Report: Synopsis A/B Comparison

- Generated at: 2026-06-09T01:42:45.253982+00:00
- Synopsis source: `C:\Users\kwonm\Kwon3802\바탕 화면\시놉시스.txt`
- Purpose: compare guide behavior with and without the supplied synopsis while keeping target country and genre constant.
- Target country: United States / `??`
- Genre: `?? ???`
- Live model path: `useLlm=true`, `generationMode=llm_with_rag`

## Saved artifacts

- case1_us_modern_romance_no_synopsis
  - payload: `docs\live_guide_case1_us_modern_romance_no_synopsis_payload.json`
  - response: `docs\live_guide_case1_us_modern_romance_no_synopsis_response.json`
  - final HTML: `docs\live_guide_case1_us_modern_romance_no_synopsis_final.html`
- case2_us_modern_romance_with_synopsis
  - payload: `docs\live_guide_case2_us_modern_romance_with_synopsis_payload.json`
  - response: `docs\live_guide_case2_us_modern_romance_with_synopsis_response.json`
  - final HTML: `docs\live_guide_case2_us_modern_romance_with_synopsis_final.html`

## Run summary

| Case | Synopsis | Mode | LLM | Policy cards | Response focus |
|---|---:|---|---|---:|---|
| case1_us_modern_romance_no_synopsis | no | country_genre_guide | llm_with_rag / gpt-4.1-mini | 0 | genre/country baseline reading |
| case2_us_modern_romance_with_synopsis | yes | synopsis_country_recommendation | llm_with_rag / gpt-4.1-mini | 18 | specific work-level reading |

## case1_us_modern_romance_no_synopsis

- Synopsis present: `False`
- Mode: `country_genre_guide`
- Policy card count: `0`

### Core appeal / input reading
- 로맨스
- 현대 배경

### Assumptions / limits from model
- 시놉시스 부재로 구체적 소재나 플롯은 확인 불가
- 미국 플랫폼 내 판타지 계열과 로맨스 판타지 태그가 강세임

### Executive summary
- 입력된 작품은 미국을 대상 국가로 한 현대 로맨스 장르입니다.
- 시놉시스가 없으므로 작품별 구체 소재나 관계, 수위 요소는 확정하지 않고, 장르 및 대상 국가 기반의 일반적 시장 데이터를 활용해 분석했습니다.
- 미국 대상 플랫폼에서 인기 있는 작품들은 판타지, 모험, 액션, 성장형 판타지(Progression), 그리고 로맨스 장르가 중복 노출되는 경향이 강합니다.
- 입력된 '현대 로맨스' 장르는 미국 주요 플랫폼 인기 순위 내에서 직접적으로 관찰되지는 않았으나, 로맨스가 포함된 하위 장르(예: 로맨스 판타지)는 빈번하게 보입니다.

### Market interpretation
- 미국 현지 주요 웹소설 플랫폼에서는 로맨스 및 판타지 요소가 결합된 장르가 상위권에서 많이 노출됩니다.
- 단독 현대 로맨스 장르는 시범 데이터 내에서는 상대적으로 적게 노출되거나 태그로 구분되지 않는 경향이 있습니다.
- 플랫폼에서는 로맨스와 판타지를 결합한 태그(예: Romance Fantasy)를 통해 장르 특성을 쉽게 파악합니다.
- 시놉시스 부재 시 작품은 노출 면에서 불리할 수 있으며, 플랫폼 독자에게 주요 매력점이 명확히 드러나지 않을 위험이 있습니다.
- 대중적 플랫폼에서 인기 장르와 태그 흐름에 비추어 볼 때, 순수 현대 로맨스 작품은 '로맨스 판타지'나 '액션 판타지'에 비해 노출 및 발견 가능성이 적을 수 있습니다.

### Policy checks
- 현재 제공된 입력과 데이터 내에서 미국 주요 플랫폼 별 별도의 위반 혹은 규제 우려 키워드는 감지되지 않았습니다.
- 연령 등급, 선정성, 폭력성 등에 관한 플랫폼별 규정은 시장 분위기와 분리하여 반드시 별도 확인이 필요합니다.
- 시놉시스가 없어 만큼 작품 내 구체적 민감 요소 파악은 불가하므로 게시 전 세부 내용에 따른 자체 점검 권장합니다.

### Tag / copy guidance
- 미국 주요 플랫폼에서는 'Romance Fantasy', 'Action Fantasy' 등 복합 장르 태그가 빠르게 작품 특성을 파악하는 데 중요합니다.
- 'Ongoing'(연재 중), 'Wait Until Free'(무료 기다리기) 등 상태 태그도 독자 유입에 영향을 미칩니다.
- 로맨스와 판타지/모험 장르가 결합된 작품들이 높은 가시성을 얻고 있다는 점을 참고하세요.
- 입력 장르인 '현대 로맨스'만으로는 태그 포함이 적어, 노출과 독자 접근성 측면에서 참고할 만한 장르 조합을 확인하는 것도 유용합니다.

## case2_us_modern_romance_with_synopsis

- Synopsis present: `True`
- Mode: `synopsis_country_recommendation`
- Policy card count: `18`

### Core appeal / input reading
- 사랑과 상처 치유
- 작가와 작가 간 계약관계 및 멜로 과외
- 로맨틱 코미디적 요소
- 감정적 성장과 내면 갈등

### Assumptions / limits from model
- 상처, 혐오 표현이 일부 존재할 수 있음
- 작가 관계 및 전 연인 트라우마와 회복을 주요 소재로 함
- 잔혹성 및 약간의 폭력 표현 가능성 있음
- 일부 성인 요소가 포함될 가능성 있음

### Executive summary
- 대상국가는 미국이며, 입력된 장르는 '현대 로맨스'입니다.
- 시놉시스가 있어 작품의 주요 소재, 관계, 수위 관련 요소를 상세히 조심스럽게 추정했습니다.
- 미국 주요 플랫폼(Wattpad, Tapas 등) 내 순위 상위 작품과 비교했을 때, 판타지, 모험, 액션, LitRPG, 로맨스 등의 태그가 자주 나타나는 반면, 입력된 현대 로맨스 장르 및 시놉시스에서 추정한 일부 요소는 이번 수집 데이터에서 직간접적으로 관찰되지 않았습니다.
- 입력 시놉시스에 기반한 민감 표현(혐오, 잔혹 등), 저작권 및 판매 관련 사항 등은 미국 현지 플랫폼별 정책에 따라 게시 전 반드시 검토가 권장됩니다.

### Market interpretation
- 미국 내 주요 웹소설 플랫폼에서는 현대 로맨스 장르가 판타지·모험·액션 등과 혼합되는 경향이 많으며, 이 작품은 다소 현실적이고 감정 중심의 소재로 플랫폼 내 노출 빈도는 상대적으로 낮을 수 있습니다.
- 플랫폼 노출 상위 작품들이 판타지 및 이세계 설정이 강한 반면 본 작품은 현실 기반 로맨스로, 미국 독자에게는 작품 소개나 태그 설정을 통해 장르적 차별점과 독특성을 명확히 보여주는 것이 중요합니다.
- 공감과 상처 치유 스토리, 작가 두 명의 계약 관계 같은 소재는 정서적 깊이를 중시하는 독자군에 긍정적으로 보일 수 있으나, 플랫폼별로는 스릴러, 복수 등 강한 갈등 요소와의 조합도 요구될 수 있습니다.
- 미국 플랫폼에서 작품의 상처 및 혐오 표현은 민감하게 다뤄질 수 있으니 게시 전 관련 표현 유무를 철저히 검토해야 하며, 저작권 및 판매 권한도 정확히 확인해야 합니다.

### Policy checks
- Tapas 정책에 따르면 타인 또는 특정 집단에 대한 증오·차별·괴롭힘 표현은 금지되어 있으며, 관련 내용이 발견되면 수정 또는 삭제해야 합니다.
- 성적 콘텐츠와 관련해 미성년자 성적화는 절대 허용되지 않으며, 누드 및 성행위 묘사 시에는 이미지와 텍스트 모두를 사전 점검하여 적합한 연령 등급을 부여해야 합니다.
- 잔혹하거나 폭력성을 조장·미화하는 내용은 삭제 또는 비폭력적으로 수정해야 하며, 자해 미화 표현 역시 제거하거나 적절한 조치를 해야 합니다.
- 저작권 침해(팬아트, AI 생성 이미지 등) 여부를 확인하고, 모든 텍스트와 이미지는 직접 창작했거나 사용 권한이 있는지 명확히 해야 합니다.
- Wattpad 정책에 따라 자해, 자살, 과도한 폭력 묘사는 연령 제한 조치가 필요하거나 삭제 요구가 있을 수 있으며, 특정 민감 주제에 대해 명확한 서사나 회복과정을 포함해야 허용됩니다.
- 모든 플랫폼은 게시 전에 작품의 콘텐츠 가이드라인과 이용약관, 행동 강령을 상세히 확인할 것을 권고합니다.

### Tag / copy guidance
- 입력된 현대 로맨스 장르는 미국 플랫폼에서 판타지나 액션장르와 대비되는 현실적 로맨스로 분류될 가능성이 있습니다.
- 시놉시스 내 계약 관계, 전 연인 트라우마, 상처 치유, 성장형 로맨스, 작가 간 멜로 과외 등 소재는 ‘감정 성장’, ‘계약 멜로’, ‘로맨틱 코미디’ 태그 후보가 될 수 있습니다.
- 다만 현지에서 로맨스 장르 내 ‘혐오 표현’이나 ‘잔혹성’ 관련 태그는 조심스럽게 다뤄질 필요가 있으므로, 민감 소재는 별도 경고 또는 연령 정책에 따라 관리해야 합니다.
- 미국 내 인기 플랫폼에서 판타지 및 로맨스 판타지 태그가 각광받으니, 만약 현실 로맨스로만 분류된다면 플랫폼 내 노출 경로가 다소 제한될 수 있으므로 태그 선택에 신중함이 필요합니다.

## Observed difference

- Case 1 stayed in `country_genre_guide`: it produced a broad United States + modern romance baseline, with no synopsis-specific work reading and no policy cards.
- Case 2 switched to `synopsis_country_recommendation`: it used the supplied synopsis packet to produce a richer work-level reading and increased policy attention cards to 18.
- The synopsis materially changed the guide surface: the result can now discuss author/protagonist setup, thriller-vs-romance contrast, emotional healing, contract/coaching relationship, and content sensitivity around murder/blood/triller terms.
- This supports the current product hypothesis: synopsis presence should not be a minor optional field; it changes the guide contract and expected output shape.

## Caveats

- Current implementation still accepts the rich synopsis packet as one long `synopsis` string. It does not yet parse title/genre/keywords/one-line/characters into separate first-class fields.
- For a production rich packet flow, use the supervisor + Work Understanding / Market Mapping / Policy Check / Guide Writer architecture recorded in `docs/next_omx_handoff.md`.
