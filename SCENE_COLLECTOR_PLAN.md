# SCENE_COLLECTOR_PLAN.md — 애니 표현 장면 수집기 개발 계획

상태: **개발 재개(rework) — 사용자 실사용 검수(UAT)에서 작업 흐름의 구조 문제가 발견됐다.** 작업 0~13의 자동시험·기술 검증 통과 기록은 유효하지만, 25절의 승인된 rework 계약에 따라 재작업 중이며 **사용자 직접 UAT PASS 전에는 개발 완료로 되돌리지 않는다.** 회사 PC operational smoke check는 그 이후로 미룬다.

이 문서는 `FIRST_VIDEO.md`의 후속 학습·콘텐츠 POC에 필요한 **애니 표현 장면 수집기**의 실행 계획이다.
`FIRST_VIDEO.md`가 콘텐츠·학습 방향의 owner이며, 이 문서는 그 방향을 실제 코드로 구현하기 위한 하위 실행 계획이다.

## 1. 제품 정의

한 줄 정의:

> 사용자가 **한국어로 찾고 싶은 뜻을 입력하면**, AI가 일본어 검색 후보를 만들고, Nadeshiko의 실제 애니 대사 자료에서 사용자가 좋아하는 작품의 장면을 찾아, 영상·원문·읽기·앞뒤 문맥·한국어 번역을 한 화면에서 검수하고 제작용으로 저장하는 Windows 로컬 프로그램을 만든다.

첫 버전의 핵심 가치는 새 검색엔진을 만드는 것이 아니다.
이미 존재하는 공식 SDK와 검증된 라이브러리를 사용하고, **까막눈에 필요한 한국어 중심 작업 흐름만 얇게 연결**한다.

## 2. 사용자 기준과 강한 제약

- 사용자는 일본어 자판 입력을 기본 작업으로 하지 않는다.
- 검색 시작점은 **한국어 의미 입력**이다.
- 일본어 표현 후보 생성은 프로그램 자체 규칙이 아니라 **선택한 AI 모델 호출**이 담당한다.
- AI 결과는 진실로 취급하지 않고 **Nadeshiko 실제 대사 corpus로 검증**한다.
- AI 모델은 GPT 하나에 종속하지 않는다. 설정으로 서비스·모델을 교체할 수 있어야 한다.
- 프로그램은 이동식 SSD에서 사용하고 집/회사 Windows PC에서 같은 작업 상태를 이어간다.
- 집/회사에서 SSD 드라이브 문자는 동일하게 맞춰져 있지만, 그 사실을 이유로 경로를 코드에 하드코딩하지 않는다.
- SSD 전체 구조는 사용자 영역이다. 프로그램은 **사용자가 지정한 작업 데이터 위치**만 관리한다.
- 사용자 환경에 따라 달라지는 경로·모델명·후보 수·작품 목록·검색 제한 등을 Python 코드에 하드코딩하지 않는다.
- 기술 문서와 사용자 화면 설명은 가능한 한 한국어를 우선한다. API·SDK·라이브러리명·코드 식별자처럼 필요한 경우에만 영어를 사용한다.

## 3. 이전 자체 구현 계획에서 폐기하는 범위

첫 버전에서는 다음을 직접 만들지 않는다.

- Nadeshiko HTTP 통신·인증·재시도·페이지 순회 기능
- OpenAI/Gemini/Claude/Ollama별 별도 통신 계층
- 자체 자막 검색엔진
- Jiten 자동 연동과 표현 점수화
- AniList 인기 점수 자동 반영
- Jimaku 자동 대체 검색
- 의미 벡터 검색·자동 군집화
- 음향 특징 분석
- 감정 자동 판정
- 화면 유사도·다양성 자동 순위
- FiftyOne 검수 환경
- FFmpeg 기반 자동 영상 재가공
- 자동 영상 편집
- 서버·클라우드·계정·다중 사용자 기능

`Nadeshiko 수록 범위가 실제 병목으로 확인되기 전에는 로컬 자막 색인이나 Jimaku 대체 경로를 구현하지 않는다`는 원칙은 그대로 지켜졌다.
2026-08-28 실제 제작 대상 작품군에서 Nadeshiko 미수록 작품이 확인되어 이 진입 조건이 충족됐고, 그에 따라 **사용자가 직접 확보한 일본어 timed subtitle의 작품 단위 로컬 색인**만 fallback으로 도입했다(작업 8 이후 확장 참조). 원칙의 폐기가 아니라 원칙이 정한 조건 충족에 따른 진행이다.
Jimaku 자동 대체 검색·자동 다운로드는 여전히 구현하지 않는다.
후보를 사람이 검수하기 전에 자동 감정·음향 순위 시스템부터 만들지 않는다.

## 4. 조사 후 채택한 기존 해결책

### Nadeshiko 공식 Python SDK

직접 API 래퍼를 만들지 않고 `BrigadaSOS/nadeshiko-sdk-python`을 사용한다.
현재 공식 SDK는 다음을 이미 제공한다.

- API 키 인증
- `search`
- `iter_search`를 통한 페이지 자동 순회
- `search_media`, `get_media`, `list_media`
- `get_segment`
- `get_segment_context`
- `get_me`를 통한 사용자/사용량 확인
- 네트워크 오류·429·5xx 재시도
- 오류 코드 처리
- 장면의 image/audio/video URL

우리 코드의 `nadeshiko.py`가 생기더라도 **공식 SDK를 우리 자료형과 작업 흐름에 연결하는 얇은 연결 코드**만 둔다.

### Instructor + Pydantic

AI가 필요한 일은 복잡한 자율 에이전트가 아니라:

1. 한국어 의미 → 일본어 검색 후보
2. 실제 일본어 문맥 → 한국어 번역·쓰임

두 종류의 구조화 결과 생성이다.
따라서 첫 버전은 `Instructor`와 `Pydantic`을 사용한다.

목표:
- OpenAI, Google, Anthropic, Ollama 등 여러 서비스 중 설정으로 선택
- 결과를 Pydantic 자료형으로 검사
- 잘못된 구조의 응답 재시도
- 프로그램 본체가 특정 AI 회사 SDK에 강하게 종속되지 않게 함

`지원 가능`과 `실제 검증 완료`는 구분한다.
첫 버전에서 최소 **서로 다른 두 AI 서비스**를 실제로 교체해 같은 자료형이 반환되는지 확인한다.

### pydantic-settings

설정 로딩과 자료형 검사는 `pydantic-settings`를 우선 사용한다.
별도 대형 설정 체계를 추가하지 않는다.

관리 대상 예:
- 작업 데이터 위치
- 선택한 AI 서비스/모델
- 검색 후보 수
- Nadeshiko 검색 제한
- 캐시 정책
- 화면 관련 실행 설정

비밀키는 코드에 하드코딩하지 않는다.
새로 추가되는 AI API 키는 공개 설정 예제와 분리한다.

### SQLite

단일 사용자 로컬 작업 상태는 Python 표준 SQLite로 저장한다.
서버형 데이터베이스나 별도 벡터 데이터베이스를 두지 않는다.

### 개발 도구

- Python 3.11 이상
- uv
- pytest
- Ruff

화면 기술은 아직 확정하지 않는다.
NiceGUI와 pywebview 중 실제 MP4 연속 재생·Windows 실행 시험을 통과한 쪽 하나만 채택한다.

## 5. 전체 사용자 흐름

```text
한국어 의미 입력
↓
선택한 AI 모델이 일본어 검색 후보 3~5개 생성
↓
Nadeshiko에서 실제 대사 검색
↓
사용자 선호작 안에서 실제 결과가 있는 표현만 제시
↓
사용자가 목표 일본어 표현 선택
↓
정확 동일표현 검사
↓
중복 제거
↓
남은 후보에만 앞뒤 문맥 조회
↓
필요한 후보를 묶음으로 한국어 번역
↓
영상 + 원문 + 읽기 + 문맥 + 번역 검수
↓
채택 / 예비 / 제외
↓
채택 후보 영상 저장
↓
제작용 JSON / CSV / clips 내보내기
```

사용자가 일본어를 직접 입력해야만 기능이 시작되는 구조는 실패다.

## 6. 한국어 → 일본어 검색 후보

AI 요청의 반환 형식은 자유문장이 아니라 고정 자료형으로 받는다.

개념 예시:

```python
class ExpressionCandidate(BaseModel):
    japanese: str
    reading: str
    meaning_ko: str
    register: str
```

예:

```text
입력:
다친 사람에게 괜찮냐고 물어보는 말

후보:
大丈夫ですか？
怪我してない？
平気？
```

AI가 만든 일본어 표현이 실제 애니에 존재한다고 가정하지 않는다.
각 후보를 Nadeshiko에 보내 실제 대사 결과가 있는지 검증한다.

### 검색 순서

기본:

> 일본어 후보 검색 우선

일본어 후보로 적절한 결과가 거의 없거나 검색 회수가 명백히 부족한 경우에만 **영어 의미 검색을 대체 경로**로 사용한다.

영어 검색을 모든 요청에서 자동 병행하지 않는다.
이유:
- API 요청 증가
- 관련 없는 결과 증가 가능성
- Nadeshiko 번역문 품질에 검색 결과가 과도하게 의존할 수 있음

작업 4 실제 품질 시험에서는 10/10 한국어 의도에서 일본어 후보 경로만으로 corpus-backed 결과를 회수했다.
작업 6 진입 전 recall 검증에서도 세 문제 표현은 상위 200건까지 정확 surface가 없었으므로, 단순 pagination을 제품 검색에 추가하지 않는다. 영어 fallback이나 AI 후보 튜닝은 실제 사용에서 이 제한이 병목으로 재확인될 때 다시 평가한다.

## 7. 목표 표현 잠금과 정확 동일표현 검사

사용자가 후보 중 하나를 선택하면 그 표현을 목표로 잠근다.

예:

```text
목표 = 大丈夫ですか？
```

동일표현 반복형에서 허용:

```text
大丈夫ですか？
あの、大丈夫ですか？
本当に大丈夫ですか？
```

제외:

```text
大丈夫？
大丈夫だよ
大丈夫なんですか？
```

검사 원칙:
- Unicode·공백·문장부호처럼 표기상 차이만 필요한 범위에서 정규화
- 문법 형태를 임의로 바꾸지 않음
- 목표 표면형이 실제 일본어 원문에 동일한 형태로 존재해야 함

작업 4에서 실제로 확인된 거짓 양성 예:
- `悪い`가 `気持ち悪い`에 부분 일치
- `ほんとそれ`이 서로 떨어진 `ほんと`와 `それって`에 검색됨
- `ん？なんて？`가 인용 문법의 `なんて`에 검색됨
- `今、何してるんですか？`가 비슷한 다른 `今…してるんです` 문장에 검색됨

작업 5에서 Nadeshiko 공식 `exact_match=True`를 실제 평가했지만 이것만으로는 부분 일치가 완전히 제거되지 않았고 일부 정상 표현의 회수도 줄었다. 따라서 최종 방식은 **일반 검색 → 로컬 표면형 검사 → 결과가 0개일 때만 exact 검색 fallback → 동일 로컬 검사**다.

로컬 matcher는 NFKC·Unicode 공백·끝 문장부호 차이만 완화하고 내부 문장부호와 활용형은 보존한다. Nadeshiko top-level token의 원문 offset을 표현 경계 보조로 사용하며, token 정보가 없을 때는 더 보수적으로 판정한다. `primary_surface`와 명시적 `allowed_surfaces`를 분리하고 `ExpressionCandidate.reading`을 자동 허용 표기로 승격하지 않는다.

### 한자/가나 표기 차이

```text
怪我してない？
けがしてない？
```

처럼 문법은 같지만 표기가 다른 경우는 `대표 표기`와 `허용 표기`를 분리한다.
활용형 차이와 표기 차이를 한 규칙으로 뭉개지 않는다.

## 8. 사용자 선호 작품

작품 이름 문자열을 내부 식별자로 사용하지 않는다.
Nadeshiko의 작품 public ID를 저장한다.

최소 저장 항목:

```text
Nadeshiko 작품 public ID
표시 작품명
선호도
사용자 콘텐츠 묶음
검색 사용 여부
```

기본 검색은 사용자가 이미 보고 좋아하거나 캐릭터·장면에 감정이 있는 작품을 우선한다.
미시청·무관심 작품으로 자동 확대하지 않는다.

`극장판`, `TV 소년만화` 같은 묶음은 단순 기술 분류와 분리된 **사용자 편성 기준**으로 저장한다.

작업 7에서 공식 SDK의 `search_media`·`get_media`로 작품 metadata를 조회하고 기존 SQLite v1 `media` table을 그대로 재사용했다. 내부 식별자는 Nadeshiko public media ID이며 표시명은 metadata다. preference는 nullable integer, content group은 자유 문자열/None, `is_active`가 기본 검색 포함 여부를 결정한다.

DB가 연결된 제품 검색에서는 활성 작품 ID를 `SearchFilters.media.include`로 Nadeshiko 요청 자체에 전달한다. 활성 작품이 하나도 없으면 global corpus로 자동 fallback하지 않고 명확한 오류를 낸다. 활성 작품 ID 집합은 정렬된 canonical 조건으로 Nadeshiko search cache identity에도 포함해 조건 없는 기존 cache나 다른 작품 조건과 섞이지 않게 한다.

작업 7 전체 pytest는 **84 passed, 14 skipped**, Ruff·`git diff --check` PASS, media live **1 passed**다. 실제 metadata 조회와 media-filtered 대사 검색, 동일 조건 cache hit를 확인했고 DB schema·dependency는 변경하지 않았다.

## 9. Nadeshiko 요청량 줄이기

비싼/추가 요청은 뒤로 미룬다.

```text
검색 결과
↓
정확 동일표현 검사
↓
선호작 검사
↓
중복 제거
↓
남은 후보에만 get_segment_context
↓
최종 검수 후보에만 AI 번역
```

Nadeshiko 사용량은 프로그램 시작 시 기억한 숫자를 믿지 않고 `get_me`와 실제 응답을 통해 확인할 수 있게 한다.
같은 검색을 반복할 때 불필요한 API 호출이 발생하지 않도록 로컬 캐시를 둔다.

작업 6 진입 전 recall 검증에서 `ほんとそれ`, `ん？なんて？`, `今、何してるんですか？`를 각각 상위 200 segment까지 cursor pagination으로 확인했지만 정확 surface는 0건이었다. `大丈夫ですか？`는 첫 20건에서 17건, `もう一回言って。`는 전체 17건에서 2건을 회수했다. pagination은 기술적으로 정상이나 세 문제 target의 recall을 개선하지 못했으므로 **제품 검색에는 추가 pagination을 넣지 않는다.** 이 제한은 corpus 부족·희귀/긴 AI 후보·rank 200 이후 존재 가능성·향후 영어 fallback 필요 가능성으로 기록하고 실제 사용에서 재평가한다.

작업 6에서는 Nadeshiko 원본 `SearchResponse`를 SQLite에 별도 cache하고 복원 후에도 기존 local surface matcher를 다시 적용하도록 구현했다. cache identity는 검색 문자열·`exact_match`·`take`·검색 조건을 구분한다.
작업 7부터 활성 media ID 집합도 검색 조건 JSON에 포함되며, 같은 작품 집합은 cache hit하고 다른 작품 조건이나 조건 없는 기존 cache는 재사용하지 않는다.
작업 8부터 `get_segment_context` 응답도 `(segment_public_id, context_take)` 기준으로 별도 SQLite cache에 저장한다. 같은 장면·같은 범위는 DB 재개방 후에도 SDK 응답을 복원해 재사용하고, 다른 장면이나 다른 범위는 cache miss로 처리한다.

## 10. 한국어 번역

Nadeshiko의 영어 번역을 그대로 최종 한국어 번역으로 사용하지 않는다.

최종 검수 후보에 대해:

```text
앞 대사
현재 일본어 대사
뒤 대사
Nadeshiko 번역 정보
```

를 묶어서 AI에 전달한다.

반환:

```text
직접적인 뜻
장면에 맞는 자연스러운 한국어
이 장면에서의 쓰임
```

장면 하나마다 AI를 한 번씩 호출하지 않고 여러 장면을 가능한 범위에서 묶어서 처리한다.

반드시 함께 기록:
- 사용한 AI 서비스
- 모델명
- 번역 지시문 버전
- 생성 시각
- 입력 내용 해시

같은 입력·모델·지시문 버전이면 저장된 결과를 우선 재사용한다.

작업 8에서 이 흐름을 구현했다. 정확 surface와 활성 선호작 필터를 통과해 DB의 `expression_segments`에 저장된 후보에만 `get_segment_context(take=2)`를 호출하고, 같은 작품·같은 화의 가장 가까운 previous/current/next를 순서에 의존하지 않고 고른다. 첫·마지막 장면처럼 한쪽 문맥이 없는 경우는 정상 상태로 처리한다.

여러 장면은 최대 5개씩 하나의 Instructor 구조화 요청으로 묶고 `SceneTranslationBatch`로 직접 의미·자연번역·장면 쓰임을 받는다. scene key의 중복·누락·알 수 없는 ID는 저장 전에 거부한다. `scene-translation-v1` 지시문 버전과 canonical 입력을 기존 AI cache에 연결해 service/model/version/input이 같을 때 provider를 다시 호출하지 않는다.

번역은 사용자 판정보다 먼저 존재할 수 있으므로 DB schema v2에서 `reviews.decision`을 nullable로 만들었다. AI 번역 저장은 기존 decision/notes를 보존하고, 사용자 decision 변경은 기존 번역을 지우지 않는다. 번역 provenance는 AI service/model/지시문 버전/입력 hash/생성 시각을 기록한다.

작업 8 전체 pytest는 **100 passed, 15 skipped**, Ruff·`git diff --check` PASS, translation live **1 passed**다. 실제 Google `gemini-3.6-flash`로 세 장면을 한 batch에서 번역했고 같은 DB 재실행과 reopen 후 context·AI 추가 호출 0회를 확인했다. 짧은 `大丈夫` 샘플에서는 직접 의미와 자연번역이 거의 같았지만 자연스러운 결과였고, 더 복잡한 표현 품질은 실제 사용에서 필요할 때 재평가한다.

## 11. 설정과 이동식 SSD

실제 SSD 경로는 저장소가 결정하지 않는다.

프로그램은 개념적으로 두 위치만 안다.

```text
<프로그램 위치>
<작업 데이터 위치>
```

`<작업 데이터 위치>`는 사용자가 지정한다.
그 아래의 내부 저장 구조는 프로그램이 관리할 수 있지만, SSD 전체의 폴더 구조를 프로그램이 임의로 정하지 않는다.

원칙:
- `C:\\...`, `D:\\...`, `E:\\...` 같은 사용자 환경 절대경로 하드코딩 금지
- 설정값에서 작업 위치를 읽음
- 프로그램이 관리하는 영구 자료는 지정된 작업 위치 안에 둠
- Windows/화면 라이브러리가 운영체제 임시영역을 쓰는 문제와 영구 작업 자료 위치는 별도 요구사항으로 구분

현재 요구사항은 **SSD에서 작업 자료와 설정을 들고 다니며 집/회사에서 이어서 작업**하는 것이다.
`실행한 PC에 임시파일 하나도 남기지 않는다`는 요구사항은 현재 확정하지 않는다.

## 12. SQLite 자료 구조

Task 6에서 첫 실제 schema v1을 구현했고 Task 8에서 실제 migration 원칙을 처음 사용해 schema v2로 올렸다. DB는 `<work_data_dir>/scene_collector.sqlite3`에 두고 Python 표준 `sqlite3`만 사용한다.

현재 table:

### media
- 내부 ID
- Nadeshiko 작품 ID
- 표시 작품명
- 선호도
- 사용자 콘텐츠 묶음
- 활성 여부

### search_runs
- 검색 ID
- 한국어 입력
- 생성 시각
- 사용 AI 서비스/모델
- 지시문 버전

### expressions
- 표현 ID
- 검색 ID
- 후보 순서
- 일본어
- 읽기
- 한국어 의미
- 말투 수준
- 선택 여부

### segments
- 내부 ID
- Nadeshiko 장면 ID
- 작품 연결
- 위치/화수/시작·종료 시각
- 일본어 원문
- 영상/음성/이미지 주소
- Nadeshiko 원문 응답 JSON

### expression_segments
- 표현 ID
- 장면 ID
- 표현 안의 장면 순서

같은 Nadeshiko segment를 여러 검색·표현이 공유할 수 있으므로 segment 원문을 중복 저장하지 않고 관계 table로 연결한다.

### reviews
- 표현 ID + 장면 ID
- 판정: `채택 / 예비 / 제외 / 미판정(NULL)`
- 직접 의미
- 자연번역
- 장면 쓰임
- 메모
- 번역 AI 서비스/모델
- 번역 지시문 버전
- 번역 입력 hash
- 번역 생성 시각
- 갱신 시각

AI 번역과 사용자 판정은 별도 사건이다. `decision IS NULL`이면 번역은 존재하지만 아직 사용자가 채택/예비/제외를 결정하지 않은 상태다.

### ai_cache
- 요청 해시
- 입력 해시
- 서비스/모델
- 지시문 버전
- 반환 JSON
- 생성 시각

### nadeshiko_search_cache
- 요청 해시
- 검색 문자열
- exact 여부
- take
- 검색 조건 JSON
- 원본 `SearchResponse` JSON
- 생성 시각

### nadeshiko_context_cache
- Nadeshiko 장면 public ID
- context take
- 원본 `SegmentContextResponse` JSON
- 생성 시각

현재 DB 구현 원칙:
- `SCHEMA_VERSION = 2`
- `PRAGMA user_version`으로 자료구조 버전 관리
- 모든 연결에서 foreign key 활성화와 실제 활성 여부 확인
- 명시적 transaction/rollback
- 현재 코드보다 높은 미래 schema는 write 없이 거부
- 실제 schema 변경 전 `sqlite3.Connection.backup()`으로 같은 작업 데이터 위치에 백업
- v1 → v2 migration은 backup 성공 후 한 transaction에서 reviews 재작성·context cache 생성·`user_version=2`를 수행하고 실패하면 원래 v1 상태를 유지
- WAL은 기본 활성화하지 않고 rollback journal 유지
- 새 ORM·migration framework·DB dependency는 추가하지 않음

Task 7은 기존 v1 `media` column으로 충분해 schema version을 올리지 않았고, Task 8에서 번역-before-review와 context cache가 실제 DDL 변경을 요구해 v2로 올렸다.

## 13. 영상 저장과 내보내기

Nadeshiko 후보는 우선 URL로 재생한다.
사용자가 `채택`한 장면만 필요에 따라 로컬 MP4로 저장한다.

파일명은 작품명/일본어 문장보다 안정적인 Nadeshiko 장면 ID를 기준으로 한다.

예:

```text
<segment_id>.mp4
```

최종 내보내기 최소 구조:

```text
표현별 출력 폴더/
├─ manifest.json
├─ candidates.csv
└─ clips/
```

내보내기 정보:
- 목표 표현
- 읽기
- 기본 한국어 뜻
- 작품
- 장면 ID
- 시각
- 실제 일본어
- 자연번역
- 장면 쓰임
- 채택/예비 판정

## 14. 첫 버전 화면

첫 버전은 다섯 영역이면 충분하다.

1. **표현 찾기** — 한국어 입력과 찾기
2. **일본어 표현 선택** — 실제 corpus 결과가 있는 후보 표시
3. **장면 검수** — 영상·원문·읽기·문맥·번역·채택/예비/제외
4. **선호 작품 관리** — 작품 검색·선호도·콘텐츠 묶음·활성 여부
5. **설정** — 작업 위치·AI 서비스/모델·연결 확인

통계 대시보드나 장식용 화면은 첫 버전에 넣지 않는다.

### 화면 기술 결정

화면은 개발 초기에 확정하지 않는다.
핵심 검색 기능이 먼저 통과한 뒤 작은 시험 프로그램에서:

- Nadeshiko MP4 20개 연속 탐색
- 재생/일시정지
- 다음/이전 장면 전환
- 한글·일본어 표시
- Windows 집/회사 환경 실행

을 확인한다.

NiceGUI와 pywebview 중 실제 시험에서 문제가 적은 하나만 남긴다.
NiceGUI는 현재 native mode와 PyInstaller 기반 패키징을 공식 지원하지만 Windows에서는 pywebview/EdgeChromium 계층을 사용하므로 실제 환경 확인이 먼저다.

## 15. 자동시험과 실제 API 시험 분리

일반 자동시험이 API 비용이나 Nadeshiko 사용량을 발생시키면 안 된다.

두 종류로 분리한다.

### 일반 자동시험
- 저장된 응답 예제 사용
- 인터넷 불필요
- AI/Nadeshiko 실제 호출 금지
- `uv run pytest`
- `uv run ruff check .`

### 실제 연결 시험
명시적으로 활성화했을 때만 실행.

확인:
- Nadeshiko 인증
- 사용자/사용량 조회
- 작품 조회
- 검색
- 페이지 순회
- 앞뒤 문맥
- MP4 URL
- AI 서비스 2종 구조화 출력

실제 응답의 필요한 최소 일부는 개인정보·키를 제거한 시험 자료로 저장해 이후 일반 자동시험에 사용한다.

## 16. 오류와 복구

최종 고장 시험 최소 항목:

- 인터넷 단절
- Nadeshiko 키 오류
- AI 키 오류
- 존재하지 않는 모델명
- AI가 잘못된 구조 반환
- Nadeshiko 요청 제한/사용량 소진
- MP4 다운로드 실패
- DB 잠김
- 프로그램 강제 종료
- 작업 위치 없음
- 읽기 전용 작업 위치
- 저장 중 파일명 충돌

목표는 오류 자체를 숨기는 것이 아니라 **사용자 작업 데이터를 잃지 않고 원인을 알 수 있게 하는 것**이다.

## 17. 개발 방식

앱 전체를 한 번에 생성하지 않는다.
작업을 GitHub Issue 수준으로 좁히고, 반복 규칙은 작업 폴더 안의 `AGENTS.md`로 제공한다. Codex나 Claude Code 등 실제 구현 도구가 달라져도 current truth와 저장소 규칙은 동일하다.

구현 시작 시 예상 위치:

```text
tools/
└─ scene_collector/
   ├─ AGENTS.md
   ├─ README.md
   ├─ pyproject.toml
   ├─ settings.example.toml
   ├─ .env.example
   ├─ src/
   │  └─ scene_collector/
   │     ├─ config.py
   │     ├─ models.py
   │     ├─ database.py
   │     ├─ nadeshiko.py
   │     ├─ ai.py
   │     ├─ search.py
   │     ├─ export.py
   │     └─ app.py
   └─ tests/
```

이 구조는 초기 예상이며 실제 구현에서 필요 없는 파일은 만들지 않는다.
폴더 수 자체를 아키텍처 품질로 보지 않는다.

### 하위 AGENTS.md에 넣을 핵심 규칙

- Python 3.11 이상
- 사용자 환경 절대경로 하드코딩 금지
- `tools/scene_collector` 밖의 파일은 해당 작업에서 명시적으로 요구하지 않는 한 수정 금지
- Nadeshiko API 재구현 금지, 공식 SDK 사용
- AI 회사별 자체 연결 체계 재구현 금지, Instructor 우선
- 일반 자동시험에서 실제 API 호출 금지
- 새 의존성 추가 전 현재 의존성/표준 라이브러리로 해결 가능한지 확인
- 작업 완료 후 `uv run pytest`, `uv run ruff check .`
- 현재 작업 범위 밖의 개선을 같은 변경에 끼워 넣지 않음

## 18. 개발 작업 단위

### 작업 0 — 개발 골격

목적: 기능 없이 개발 환경만 만든다.

- `tools/scene_collector` 기본 구조
- Python 3.11+
- uv
- pytest
- Ruff
- 하위 AGENTS.md
- 설정 예제
- 실제 사용자 경로/비밀키 입력 금지

통과:
- `uv sync`
- `uv run pytest`
- `uv run ruff check .`

### 작업 1 — 설정

- pydantic-settings
- 작업 데이터 위치
- AI 서비스/모델 설정
- `.env`/비밀정보 로딩
- 잘못된 설정의 명확한 오류
- 코드에 사용자 경로 없음

### 작업 2 — Nadeshiko 실제 연결 확인

- 인증
- `get_me`
- 작품 조회
- 검색
- 자동 페이지 순회
- 앞뒤 문맥
- 영상 URL
- 시험용 익명 응답 예제 저장

상태: **완료**. 실제 live test에서 인증·`get_me`·작품 조회·검색·페이지 순회·앞뒤 문맥·image/audio/video URL을 모두 확인했다.

### 작업 3 — AI 실제 연결 확인

Instructor 사용.
서로 다른 AI 서비스 최소 2개를 설정만 바꿔 실제 시험한다.
애플리케이션 검색 로직을 수정하지 않고 동일 Pydantic 자료형이 반환되어야 한다.

상태: **완료**. 실제 live test에서 OpenAI `gpt-5.4-nano`와 Google `gemini-3.6-flash`를 설정만 바꿔 호출했고, 두 provider 모두 동일 `ConnectivityProbe` Pydantic 자료형을 반환했다.

### 작업 4 — 한국어 표현 찾기

```text
한국어
→ AI 일본어 후보
→ Nadeshiko 실제 검색
→ 실제 자료가 있는 표현 후보
```

대표 시험 표현 최소 10개를 사용해 상위 후보 안에 실제 문맥상 쓸 만한 표현이 들어오는지 평가한다.

상태: **완료**. Google `gemini-3.6-flash`로 고정 한국어 의도 10개를 실제 평가했고 10/10에서 corpus-backed 후보가 하나 이상 회수됐다. AI 후보 50개 중 Nadeshiko 일반 검색 결과가 있는 후보는 44개였으나, 부분 일치 거짓 양성이 실제로 확인되어 이 수치를 유효 표현률로 해석하지 않는다. 영어 fallback 필요성은 확인되지 않았고 정확 동일표현 검사가 다음 병목으로 확정됐다.

### 작업 5 — 정확 동일표현 검사

표면형 정규화와 정확 포함 검사.
문법 변형은 제외.
한자/가나 허용 표기는 별도 관리.
작업 4에서 확인된 부분 일치 거짓 양성을 제거하고, 실제 원문에 목표 표현이 같은 표면형으로 존재하는 후보만 남긴다.

상태: **완료**. Nadeshiko `exact_match=True`를 단독 정확성 기준으로 쓰지 않고 일반 검색과 로컬 surface matcher를 결합했다. 전체 pytest **61 passed, 13 skipped**, Ruff·`git diff --check` PASS, Nadeshiko surface live **1 passed**를 확인했다. 대표 거짓 양성을 제거하면서 필수 positive를 유지했고 새 tokenizer 의존성은 추가하지 않았다.

#### 작업 6 진입 전 검색 recall 검증

상태: **완료**. 작업 번호를 새로 만들지 않은 단기 검증이다.

작업 5 live에서 `ほんとそれ`, `ん？なんて？`, `今、何してるんですか？`가 상위 20건에서 정확 surface 0건이었던 관찰을 Nadeshiko 공식 cursor pagination으로 추가 확인했다.

결과:
- 세 문제 target을 각각 상위 200 segment까지 조회했으나 정확 surface 0건
- `大丈夫ですか？`는 첫 20건에서 정확 surface 17건
- `もう一回言って。`는 전체 17건에서 정확 surface 2건
- pagination은 정상 동작했지만 세 문제 target의 회수를 개선하지 못함
- 제품 코드에는 pagination을 추가하지 않음
- rank 200 이후 존재 가능성, corpus 부족, AI 후보의 희귀/장문 문제, 향후 영어 fallback 필요 가능성은 제한으로 기록

따라서 검색 recall 검증은 닫고 기존 계획의 작업 6으로 이동한다.

### 작업 6 — 저장·캐시·자료구조 버전

- SQLite
- 검색 기록
- 표현
- 장면
- 검수
- AI 캐시
- `PRAGMA user_version`
- 구조 변경 전 백업

상태: **완료**. Python 표준 `sqlite3`만 사용해 v1 schema를 구현했고 전체 pytest **72 passed, 13 skipped**, Ruff·`git diff --check` PASS를 확인했다. 파일 DB 재개방 후 검색·표현·공유 segment·review·AI/Nadeshiko cache가 유지되는 것을 검증했다. AI cache와 Nadeshiko raw search cache는 실제 코드 경로에 연결해 동일 fake 외부 호출이 재실행되지 않는 것을 확인했다. `PRAGMA user_version=1`, foreign key, 명시적 transaction/rollback, `Connection.backup()` 기반 구조 변경 전 백업을 적용했고 WAL·ORM·새 dependency는 추가하지 않았다.

### 작업 7 — 선호 애니 관리

Nadeshiko 작품 검색 → 작품 ID 저장 → 선호도·콘텐츠 묶음·활성 여부.

상태: **완료**. 공식 `nadeshiko-sdk==2.3.7`의 `search_media`·`get_media`·`SearchFilters.media.include`를 사용해 Nadeshiko public media ID 기반 작품 관리와 활성 선호작 검색을 연결했다. 기존 SQLite v1 `media` table을 재사용해 preference/content_group/is_active를 보존하며 metadata를 갱신하고, DB가 연결된 제품 검색은 활성 작품이 없을 때 global corpus로 자동 fallback하지 않는다. 활성 media ID 집합은 Nadeshiko search cache 조건에도 포함한다. 전체 pytest **84 passed, 14 skipped**, Ruff·`git diff --check` PASS, media live **1 passed**를 확인했고 schema와 dependency는 변경하지 않았다.

현재 제한: 실제 사용자 선호작 목록은 UI 전이라 아직 직접 등록 경로가 필요하고, 선호작 corpus로 좁힐수록 일부 표현 recall이 더 낮아질 수 있다. 이 제한은 실사용에서 확인된 경우에만 검색 전략을 다시 연다.

### 작업 8 — 한국어 장면 번역

정확 후보의 앞/현재/뒤 문맥을 묶어서 번역.
모델·지시문 버전·입력 해시 저장.

상태: **완료**. 정확 surface와 활성 선호작 조건을 통과해 저장된 장면에만 `get_segment_context(take=2)`를 호출하고, 같은 작품·화의 가장 가까운 앞/뒤 대사를 선택한다. context는 `(segment_public_id, take)` 기준으로 SQLite에 캐시한다. 여러 장면은 최대 5개씩 하나의 Instructor 구조화 요청으로 번역하며 `SceneTranslationBatch`의 scene key 중복·누락·미지 ID를 저장 전에 거부한다. 기존 AI cache를 `scene-translation-v1` 지시문과 canonical 입력으로 재사용한다.

번역은 사용자 판정보다 먼저 존재할 수 있으므로 `SCHEMA_VERSION = 2`로 올려 `reviews.decision`을 nullable로 만들고 번역 provenance를 추가했다. v1 DB는 `Connection.backup()` 후 한 transaction에서 v2로 migration하며 실패 시 v1 원본을 유지한다. AI 번역 저장과 사용자 decision/notes 수정 경로를 분리해 서로 덮어쓰지 않는다.

전체 pytest **100 passed, 15 skipped**, Ruff·`git diff --check` PASS, translation live **1 passed**를 확인했다. 실제 Google `gemini-3.6-flash`에서 세 장면을 한 batch로 번역했고 같은 DB 재실행과 reopen 후 Nadeshiko context·AI provider 추가 호출이 발생하지 않았다. 이번 짧은 샘플의 번역 품질은 자연스러웠으며, 복잡한 생략·간접 표현은 실제 사용에서 필요할 때 재평가한다.

### 작업 8 이후 확장 — 로컬 timed subtitle fallback

작업 번호를 새로 만들지 않은 확장이다. 3절의 진입 조건(`Nadeshiko 수록 범위의 실제 병목 확인`)이 2026-08-28 실제 제작 대상 작품군에서 충족되어 진행했다.

배경: 실제 제작 대상 작품군에 Nadeshiko 미수록 작품이 있어, 사용자가 직접 확보한 일본어 timed subtitle(SRT/ASS)을 해당 작품의 검색 corpus로 쓴다. 자막 파일은 저장소 밖 사용자 위치에 두고 자동 다운로드는 없다.

POC(`experiments/subtitle_poc/search_subtitles.py`): 자막 폴더를 pysubs2로 파싱하고 기존 Task 5 surface matcher를 그대로 재사용해 **표현 → 화수 → 타임코드 → 실제 원본 장면 탐색** 경로를 검증했다. 저장소 밖 진격의 거인 S1 5화 fixture에서 1,559개 cue를 파싱해 시험 표현 5개 전부 실제 장면과 정확한 타임코드를 회수했다. 화수는 범용 파일명 패턴만 사용하고 작품별 전용 로직은 없다. 자막과 원본 판본 차이로 ±15초 안팎의 offset이 화마다 있을 수 있다.

제품 통합(`claude/scene-collector-subtitle-poc`, `be0574a`):
- DB `SCHEMA_VERSION = 3`: `media.source`('nadeshiko'/'local')를 추가하고 로컬 작품의 `nadeshiko_media_id`를 NULL로 허용(CHECK로 연동)하며 `local_segments` 색인 table을 추가했다. media 재작성은 SQLite 공식 절차(transaction 밖 foreign key OFF, commit 전 `PRAGMA foreign_key_check`)를 따르고, 기존 v1/v2 DB는 단계별 `backup_before_schema_change()` 후 순차 migration한다.
- `subtitles.py`: 자막 폴더 파싱·화수 추정·작품 단위 색인. 같은 작품 재색인은 기존 색인을 통째로 교체한다.
- 통합 검색: 활성 Nadeshiko 작품은 기존 공식 검색·cache 그대로, 활성 로컬 작품은 정규화 LIKE 1차 축소 후 기존 surface matcher 최종 판정. 로컬 작품은 Nadeshiko media filter·cache 조건에 섞이지 않고, 활성 Nadeshiko 작품이 없으면 Nadeshiko API를 호출하지 않는다(`response=None`).
- 새 dependency는 검증된 `pysubs2==1.8.1` 하나만 고정 추가했다.

코드 검수(2026-08-28): **PASS**. main 대비 변경이 `tools/scene_collector` 안으로 한정되고, 전체 pytest **112 passed, 15 skipped**(live 전부 skip, API 비용 0)·Ruff·`git diff --check` PASS를 확인했다. migration은 실제 시드된 v1/v2 DB로 데이터·참조 보존과 실패 주입 시 rollback까지 검증됐다.

상태: **완료 — 코드 검수 PASS 후 사용자 승인 하에 main에 fast-forward로 반영됐다.**

여전히 범위 밖: Jimaku 자동 대체 검색·자동 다운로드, STT(Whisper 등), FFmpeg 자동 클리핑, UI, 로컬 장면의 번역·검수 저장 연결. 로컬 장면의 번역·검수 연결은 실사용에서 필요가 확인될 때 별도 작업으로 연다.

### 작업 9 — 화면 기술 확인

NiceGUI / pywebview를 작은 시험으로 비교.
Nadeshiko MP4 연속 재생과 Windows 실행이 더 안정적인 쪽 하나만 선택.
시험 후 선택하지 않은 화면 코드는 제거.

상태: **완료 — NiceGUI 3.16.0(native mode) 선택, main 반영.** NiceGUI 3.16.0과 pywebview 6.2.1을 같은 조건(같은 영상 목록·같은 창 구성·같은 WebView2/EdgeChromium backend, `Edg/151` user-agent 확인)의 작은 Windows probe로 실측 비교했다. pywebview에서 js_api public 속성의 JS 재귀 노출로 인한 실제 창 hang이 관찰됐고, Task 10 다섯 화면을 직접 HTML/JS bridge로 만드는 부담까지 근거로 NiceGUI를 선택했다. pywebview probe 코드와 직접 dependency는 제거했고 pywebview는 `nicegui[native]`의 transitive dependency로만 남는다.

최신 main 위 재검증(subtitle fallback 반영 후)에서도 실제 Nadeshiko 샘플 video_url 자산 20개로 연속 전환(20→1 순환, 역방향 포함)·재생·일시정지·다음/이전·일본어/한국어 표시·Windows native 실행·정상 종료 후 프로세스 잔류 없음이 전부 PASS였고, 전체 pytest **112 passed, 15 skipped**·Ruff·`git diff --check` PASS를 확인했다.

**이번에 샘플링한 20개 자산에서 관찰된 "정지 화면 + 대사 음성" MP4 형태는 해당 샘플에 한정된 관찰이며, Nadeshiko 전체 corpus의 모든 video_url 자산으로 일반화하지 않는다.** 움직이는 MP4 재생은 ffmpeg 로컬 테스트 영상으로 별도 검증했다.

### 작업 10 — 실제 사용자 화면

기존에 통과한 검색·저장 기능만 연결한다.
화면 개발 중 새로운 검색 알고리즘을 만들지 않는다.

상태: **완료 — NiceGUI(native mode) 5영역 화면, main 반영.** 표현 찾기 / 일본어 표현 선택 / 장면 검수 / 선호 작품 / 설정을 얇은 adapter(`ui_controller`)로 기존 `search_expressions`·`translate_expression_scenes`·`set_review_decision`·선호작 관리에 연결했다. DB schema·검색 알고리즘·dependency는 변경하지 않았고, 화면 상태는 클라이언트(창)별로 분리했다(검증 중 발견된 상태 공유 버그 수정). UI는 활성 작품 없음("검색에 사용할 활성 작품이 없습니다...")과 실제 corpus 0건을 구분해 안내하고, 비밀키 값은 화면에 출력하지 않는다.

Windows native E2E로 **작품 추가/활성화 → 한국어 검색 → corpus-backed 후보 → 장면 검수 → 번역 → 채택 저장 → 종료(프로세스 잔류 0) → 재실행 → 상태 복원**을 전부 PASS했다. 전체 pytest **117 passed, 15 skipped**, Ruff·`git diff --check` PASS.

알려진 제한(확장하지 않고 기록만): 로컬 자막 작품은 목록 표시만 되고 활성/선호도 편집은 Nadeshiko 작품만 가능, 로컬 장면의 판정 저장은 범위 밖, 재실행 복원은 장면이 남은 가장 최근 검색 1건 기준, 탭 전환 직후 짧은 레이아웃 흔들림(기능 무관).

### 작업 10.5 — curated 작품 풀 + 체크 활성화 UI

한국 인기/인지도 기준으로 조사·채택된 curated 후보를 선호 작품 탭에 표시하고, 사용자 체크만으로 기존 검색 pool을 바꾼다.

실행 계약:
- curated 후보 **97개: A군 63 / B군 34**, Tier 1/2/3, 한국 인기 근거 등급 A/B/C를 데이터로 유지한다.
- 각 후보는 Nadeshiko/Jimaku source availability를 가진다: Nadeshiko 직접(부분 커버 포함) 또는 Jimaku 일본어 SRT/ASS 확인 경로.
- **하나의 사용자 체크 항목(프랜차이즈)이 여러 Nadeshiko media entry에 연결될 수 있다**(예: 체인소 맨 = TV + 레제편). 사용자는 항목 하나만 체크하고 내부 entry는 함께 활성/비활성한다.
- 기존 `media.is_active` 검색 구조를 그대로 유지한다. **DB schema 변경을 기본값으로 하지 않는다.** 검색 알고리즘 변경 없음.
- Jimaku 자동 다운로드 없음. Jimaku 경로 작품은 자막 준비·색인 후에만 활성화할 수 있고, 준비 전에는 "자막 준비 필요"로 정직하게 표시한다.
- **사용자 체크만 활성화 상태를 바꾼다.** 프로그램/AI가 후보를 자동 활성화하지 않으며, 97개를 DB에 자동 삽입하지 않는다.
- 완료 후 원래 작업 11로 복귀한다.

상태: **완료 — curated 97개 + A/B 필터 + 사용자 체크 기반 is_active 연결을 구현했고 Windows native E2E PASS.**

실측 요약:
- 선호 작품 탭에서 전체 97 / A군 63 / B군 34 표시 확인.
- 체인소 맨 + 귀멸의 칼날 + 스즈메의 문단속 체크 — 사용자 선택 3개 → **Nadeshiko media entry 4개 활성**(체인소 맨 = TV + 레제편).
- 실제 검색의 cache/filter 조건에서 **정확히 그 4개 ID만** 사용됐음을 SQLite로 교차 확인.
- 체인소 맨 해제 후 다음 검색 filter에서 TV+레제편 **모두 제외** 확인.
- 종료/재실행 후 체크 상태 복원 확인.
- 전체 pytest **125 passed, 15 skipped**, Ruff·`git diff --check` PASS.
- DB schema·검색 알고리즘·dependency 무변경.

제한:
- Jimaku-only 38개는 자막 확보·색인 전에는 체크할 수 없다.
- 실제 Jimaku 파일의 판본/offset/품질은 해당 작품을 실제 사용할 때 확인한다.
- 로컬 색인 연결은 현재 표시명 정확 일치 규약이다(curated 한국 제목으로 색인).
- `nadeshiko_partial` 항목 중 entry의 전체 시즌 커버 범위가 미확정인 항목이 있다.

### 작업 11 — 영상 저장·내보내기

채택 MP4 저장, JSON/CSV 출력, 중복 다운로드 방지.

상태: **완료.** 채택(decision='채택') Nadeshiko 장면의 MP4 저장과 `accepted_scenes.json`/`accepted_scenes.csv` 출력을 구현했다.

- 영상 identity는 `segment_public_id`이며 `exports/videos/<segment_public_id>.mp4` 하나로 저장해 중복 다운로드를 방지한다. **동일 segment가 여러 표현에서 채택되면 MP4는 1개, metadata 관계 row는 각각 유지**한다.
- 다운로드는 `.part` → atomic replace, manifest도 temp → replace로 작성해 중간 실패가 기존 정상 파일을 깨지 않는다. 0 byte 파일은 완료로 취급하지 않는다.
- manifest의 `video_file`은 exports 기준 상대경로라 SSD 이동 후에도 유지된다.
- DB schema v3 유지, dependency 변경 없음, Nadeshiko SDK 업그레이드 없음(실제 blocker 미관찰).
- Windows native 실측: 실제 채택 장면 2개의 MP4 2개 저장과 ffprobe container 확인, **두 번째 export에서 다운로드 0·기존 파일 재사용** 확인.
- 전체 pytest **132 passed, 15 skipped**, Ruff·`git diff --check` PASS.
- 로컬 자막 장면의 영상 export는 아직 범위 밖이며 화면에 그대로 안내한다.

### 작업 12 — SSD 집/회사 실행 확인

집 PC에서 검색·저장 후 종료 → SSD 이동 → 회사 PC에서 같은 상태로 이어서 검수.

상태: **기술적 portability 검증 PASS / 실제 두 번째 PC 검증은 수행하지 않음.**

- 실제 SSD work_data_dir에 baseline(활성 작품·검색 run·선택 표현·판정 3종·번역·export 산출물)을 만들고 `task12_baseline.json`에 DB·MP4·manifest SHA-256을 기록했다.
- 앱 완전 종료 후 동일 SSD 데이터를 Windows `subst`로 **다른 drive letter/절대경로**에서 열어(설정의 work_data_dir만 변경) 같은 DB가 새 DB 생성 없이 열리고 체크·검색·검수·번역 상태와 export 산출물이 그대로 복원됨을 확인했다. 열람·재-export 후에도 DB SHA-256이 baseline과 동일했고, manifest의 상대 `video_file` 덕에 기존 MP4가 재사용되어 재다운로드 0이었다.
- **실제 회사 PC 검증은 하지 않았다.** 개발 완료 기준에서는 기술적 SSD 이동성 검증까지를 완료로 보고, 실제 회사 PC 확인은 **1회 operational smoke check**(SSD 연결 → drive letter가 다르면 settings.toml의 work_data_dir 수정 → 앱 실행 → 상태 복원 확인)로 분리한다.

### 작업 13 — 고장 시험

16절 오류 목록을 실제로 시험하고 작업 데이터 보존을 확인한다.

상태: **완료.** 기존 offline 보호장치 테스트 전체 실행 PASS에 더해, 실제/주입 고장 시험으로 다음을 확인했다.

- Nadeshiko 키 오류·AI 키 오류·없는 모델명: 실제 호출 실패가 명확한 오류로 드러나고 저장 데이터 무변화, 실패한 검색 run 미저장. (인터넷 단절·사용량 소진은 같은 HTTP 오류 처리 경로로 갈음 — 별도 유발 불가.)
- 잘못된/없는 work_data_dir 거부. **손상 TOML 문법은 ConfigurationError("설정 파일 형식이 올바르지 않습니다")로 정리** — 마감 수정 반영.
- DB reopen·transaction rollback·migration 전 backup 기존 테스트 유지, **더 새로운 schema(v99) 거부 + 데이터 무변화**.
- export 고장: 다운로드 실패 시 `.part` 잔류 없음·기존 정상 MP4 보존·0 byte 미완료 처리·manifest temp→replace 보존.
- 활성 작품 0개에서 global fallback 금지, **손상 AI cache는 miss 처리**로 기존 데이터 무영향.
- **강제 종료(taskkill /F) 후 DB reopen + `PRAGMA integrity_check` ok.**
- **DB 잠김은 DatabaseError("작업 데이터베이스를 사용할 수 없습니다…")로 정리** — 마감 수정 반영. 잠금 해제 후 같은 연결·재열기 모두 정상, 데이터 보존.
- 읽기 전용 작업 위치: **미실측**(Windows에서 시스템 설정 변경 없는 안전한 재현 수단 없음). 코드의 OSError 처리 경로는 존재한다.
- 마감 수정 2건 반영 후 전체 regression **134 passed, 15 skipped**, Ruff·`git diff --check` PASS, schema v3·dependency·검색/번역/export 코드 무변경.

## 19. 개발량 추정

이전의 31~46시간 추정은 화면·복구·DB 구조 변경·공급자 교체 실제 시험을 누락해 너무 낙관적이었다.

현재 계획상 사람 개발자 기준 추정:

- 모든 외부 도구가 예상대로 동작: 약 **40시간**
- 기준 예상: 약 **52시간**
- Windows/영상/AI 호환 문제가 여러 번 발생: 약 **65~75시간**

확정 계약 시간이 아니라 불확실성 관리용 추정이었다.
작업 0~13이 개발 기준으로 완료되어 이 추정의 관리 목적은 끝났다. 남은 것은 실제 회사 PC에서의 1회 operational smoke check뿐이다.

AI 코딩 도구로 코드 작성 시간은 줄 수 있지만 실제 API 동작, Windows 영상 재생, SSD 이동, 사용자 작업 흐름 검증 시간까지 자동으로 사라진다고 가정하지 않는다.

## 20. 경력 10년차 협업 개발자 관점 검토 결과

실제 외부 개발자를 고용해 검토받았다는 뜻이 아니라, **경력 10년차 개발자가 인수·유지보수까지 책임진다고 가정한 검토 기준**을 적용한 결과다.

### 가장 큰 기술 위험

화면 기술이 아니라:

> **한국어 의도에서 만든 일본어 후보가 실제로 사용자가 찾는 표현을 안정적으로 회수하는가**

이다.

이게 실패하면 화면과 자동 순위가 좋아도 제품 가치가 없다.
따라서 검색 품질 검증이 화면 개발보다 앞선다.

### 검토에서 수정된 문제

1. **도구를 너무 일찍 확정했던 문제**
   - Pydantic AI/Dynaconf/NiceGUI 고정 계획 폐기.
   - 구조화 출력에는 Instructor, 설정에는 pydantic-settings를 우선하고 화면은 실제 시험 후 결정.

2. **외부 라이브러리 위에 다시 자체 추상화 계층을 과하게 만들 위험**
   - `BaseLLMProvider` 같은 자체 체계를 먼저 만들지 않는다.
   - Instructor의 현재 공식 사용법을 직접 활용한다.

3. **영어 검색을 모든 요청에 병행하던 계획**
   - 일본어 후보 검색 우선, 부족할 때만 영어 의미 검색.

4. **AI 결과의 재현성 부족**
   - 서비스·모델·지시문 버전·입력 해시·결과 저장.

5. **DB 구조 변경 계획 누락**
   - `PRAGMA user_version`과 변경 전 백업.

6. **이동식 SSD와 무설치·무흔적을 혼동할 위험**
   - 작업 자료 이동성과 PC 임시파일 무사용을 별도 요구사항으로 구분.

7. **모든 AI 서비스를 지원한다고 과장할 위험**
   - Instructor가 연결 가능하다는 것과 실제 검증 완료를 구분.
   - 최소 2개 서비스만 먼저 실제 교체 검증.

8. **개발시간 과소평가**
   - 기준 52시간으로 수정하고 작업 0~3 후 재산정.

9. **자동 분석 과잉**
   - 감정·음향·의미 자동 순위는 실제 수동 검수 병목이 확인될 때만 재검토.

## 21. 첫 실사용판 통과 기준

첫 버전은 다음이 모두 되어야 한다.

- 일본어 키보드 없이 한국어 입력에서 시작 가능
- 선택한 AI 모델이 구조화된 일본어 후보 생성
- 최소 2개 AI 서비스가 설정 변경만으로 교체 검증됨
- Nadeshiko 공식 SDK로 실제 대사 검색
- 선호작 안에서만 기본 검색
- 목표 표현의 잘못된 문법 변형을 최종 후보에서 제거
- 앞뒤 문맥 확인 가능
- 자연스러운 한국어 장면 번역 표시
- 영상 검수 가능
- 채택/예비/제외 상태 저장
- 프로그램 재시작 후 작업 상태 유지
- 같은 요청의 불필요한 AI/Nadeshiko 재호출 감소
- 채택 영상과 제작용 JSON/CSV 내보내기
- 동일 SSD 작업 데이터를 다른 절대경로/drive letter에서도 같은 상태로 이어서 작업 가능 (**기술적 portability PASS; 실제 회사 PC는 1회 operational smoke check 미수행**)
- 일반 자동시험은 실제 API 비용/사용량을 발생시키지 않음

## 22. 현재 하지 않는 것

다음은 실패가 관찰되기 전까지 개발하지 않는다.

- 자동 감정 분류
- 음성 억양 자동 순위
- 얼굴 인식
- 장면 화면 유사도
- 의미 임베딩/자동 군집화
- Jiten 자동 점수
- AniList 인기 점수
- Jimaku 자동 검색·자동 다운로드
- 로컬 애니 라이브러리 전체 자동 색인 (사용자가 직접 확보한 자막의 작품 단위 fallback 색인은 병목 확인 후 도입 — 작업 8 이후 확장 참조)
- Whisper 등 STT 대사 추출
- FFmpeg 자동 재편집
- 자동 영상 제작
- Anki 연동
- 서버/클라우드

## 23. 구현 참고 근거 — 2026-08-27 재확인

- Nadeshiko Python SDK: https://github.com/BrigadaSOS/nadeshiko-sdk-python
- Instructor 구조화 출력: https://python.useinstructor.com/
- pydantic-settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- NiceGUI Windows/native/패키징: https://nicegui.io/documentation/section_configuration_deployment
- OpenAI Codex 작업 방식/AGENTS.md: https://openai.com/business/guides-and-resources/how-openai-uses-codex/
- 기존 Python 애니 문장 채굴 참고: https://github.com/amfajar/sentence-miner
- 기존 로컬 영상/자막 검색 참고: https://github.com/solomonneas/reelgrep
- 기존 일본어 immersion 도구 참고: https://github.com/ksyasuda/SubMiner

기존 프로젝트는 필요한 기능과 구조를 참고·재사용 대상으로 보고, 하나를 억지로 통째로 fork해서 불필요한 Anki/player/색인 기능까지 끌고 오지 않는다.

## 24. 바로 다음 작업

**25절의 승인된 rework 계약을 구현 순서대로 진행한다.** 완료 조건은 자동시험이 아니라 **사용자 직접 실사용 검수 PASS**이며, 그 전에는 이 문서를 '개발 완료'로 되돌리지 않는다. 회사 PC operational smoke check와 프로젝트 본체 복귀(0화 실제 구성·후속 콘텐츠 POC)는 UAT PASS 이후에 진행한다.

## 25. Rework — 사용자 실사용 검수 반영 (승인된 실행 계약)

UAT에서 확인된 문제: 선택하지 않은 후보 전부를 Nadeshiko에 검색하고 검색 결과가 있는 표현만 보여주는 구조, 검색 응답·장면 원본·URL·캐시의 영구 저장과 시작 시 검색 자동 복원, 장면 수만큼 영상 동시 로딩, 작업 결과(판정·번역·메모)의 검색 저장 구조 종속.

승인된 새 사용자 흐름:

1. 한국어 의미 입력 → DB에 **저장 표현이 있으면 AI를 호출하지 않고** 전부 표시.
2. 없으면 AI가 그 의미의 실전 일본어 회화 표현을 **자연스러운 만큼 폭넓게(최대 20, 억지로 채우지 않음)** 생성해 표현 자산으로 저장. [표현 더 찾기]는 기존 표현 전부를 전달해 **중복되지 않는 추가분만** 저장.
3. 사용자가 **의미→표현 관계 하나를 선택했을 때만** 그 표현 하나를 Nadeshiko(활성 선호작 필터)와 로컬 자막에서 검색. 검색 응답·결과·문맥 응답은 **캐시/저장하지 않는다**(세션 한정, 재검색 = 재호출).
4. 장면 목록은 텍스트로 표시하고 **영상 플레이어는 1개** — 선택한 장면만 로딩.
5. 문맥 조회·한국어 번역은 **장면 단위 명시 요청 시에만** 실행하고, 번역 결과는 캐시가 아니라 **작업물로 DB 저장**.
6. **실제 작업한 장면만**(채택/예비/제외·번역·메모 발생 시) 저장. 내보내기는 기존 MP4 재사용, 없으면 `get_segment`로 **내보내기 시점의 현재 영상 주소**를 조회해 다운로드(오래된 video_url 저장 구조 제거).

DB 구조(SCHEMA_VERSION = 4): `media`/`local_segments` 무변경 + **표현 자산 3테이블** — `meanings`(정규화 한국어 의미 UNIQUE + 표시 원문), `expressions`(japanese UNIQUE + reading), `meaning_expressions`(관계 + **그 의미에서의 뜻/말투**) — 같은 일본어 표현이 여러 의미에 연결되고 의미마다 설명이 다를 수 있으므로 뜻/말투는 관계에 둔다. 실제 작업은 `work_scenes`(**meaning_expression_id 기준**, segment_public_id·작품·화수·시간·원문 스냅샷·판정·번역·provenance·메모, URL·raw 응답 미저장, UNIQUE(관계, segment)). 내보내기 manifest는 해당 작업이 연결된 **정확한 한국어 의미 1개**를 출력한다(여러 의미를 합쳐 쓰지 않음).

의미 정규화: NFKC → 양끝 공백 제거 → 연속 공백 축약 → 끝의 단순 문장부호 `? ! .`(전각 `？！．。` 포함) 제거까지만. 형태소 분석·자동 병합은 하지 않는다.

제거 대상: `ai_cache`·`nadeshiko_search_cache`·`nadeshiko_context_cache`, `search_runs`·구 `expressions`·`expression_segments`·`segments`·구 `reviews`, 검색 결과 저장(`save_search_result`)과 시작 시 검색 복원, 선택 전 전 후보 검색.

설정: `candidate_count`는 의미가 달라졌으므로 **값을 승계하지 않는다** — 새 `expression_generation_limit`(기본 20)을 사용하고, 구 키만 있는 설정에서도 기본값 20을 쓴다. 실제 settings.toml은 구현 과정에서 `expression_generation_limit = 20`으로 갱신한다. `nadeshiko_take`는 유지.

로컬 자막 범위: 선택 표현 검색 시 병행 검색해 **해당 작품에 그 표현이 존재하는지 확인하는 참고 결과로만** 표시한다. 이번 rework에서 영상 로딩·판정 저장·work_scenes 저장·내보내기는 **Nadeshiko 장면으로 한정**하며 로컬 자막 작업 장면 지원을 새로 확장하지 않는다.

v3 → v4 migration: 기존 자동 pre-schema backup 유지 + **실제 SSD DB 사본에 먼저 migration을 실행해 보존(선호 작품·로컬 자막·기존 표현·의미 연결·판정·번역·메모)을 확인한 뒤에만 실 DB에 실행**한다. v3의 표현·의미·실작업(reviews 중 판정/번역/메모 보유분)은 새 구조로 이관하고, 캐시·검색 이력·segment 원본·URL은 이관하지 않는다. 실패 시 rollback으로 v3 원본 유지.

완료 조건: 한국어 입력 → 저장 표현 확인/AI 생성 → 표현 선택 → 장면 검색 → 장면 하나 선택 → 영상 확인 → 필요시 문맥/번역 → 판정/메모 → 종료·재실행 후 보존 확인 → 내보내기까지 **실제 사용자가 직접 사용해 PASS를 선언**하는 것. 21절의 통과 기준도 rework 완료 시 새 흐름 기준으로 갱신한다.

작업 0 — 개발 골격, 작업 1 — 설정 로딩·검증, 작업 2 — Nadeshiko 실제 연결 확인, 작업 3 — AI 실제 연결 확인, 작업 4 — 한국어 표현 찾기, 작업 5 — 정확 동일표현 검사, 작업 6 — 저장·캐시·자료구조 버전, 작업 7 — 선호 애니 관리, 작업 8 — 한국어 장면 번역은 완료되어 `main`에 반영됐다.
검색 recall 검증도 닫았다. 세 문제 target을 상위 200건까지 확인해도 정확 surface가 없었고 pagination의 제품 적용 이득이 확인되지 않았으므로 검색 계층을 더 늘리지 않는다.
Task 6에서는 SQLite v1 schema, 파일 DB 재시작 복원, review, AI cache, Nadeshiko raw search cache, foreign key, 명시적 transaction/rollback, `PRAGMA user_version`, 구조 변경 전 backup까지 offline으로 검증했다.
Task 7에서는 Nadeshiko public media ID 기반 선호작 관리와 `SearchFilters.media.include` 기반 활성 작품 검색을 구현했다. media 조건은 Nadeshiko cache identity에도 포함되며 활성 작품이 없으면 global corpus로 자동 확대하지 않는다.
Task 8에서는 정확 후보에만 앞뒤 문맥을 조회하고 여러 장면을 한 AI 구조화 요청으로 한국어 번역한다. context cache와 기존 AI cache를 재사용하며, DB schema v2에서 번역-before-review 상태와 provenance를 저장하고 v1 → v2 backup/migration을 검증했다.
작업 8 이후 확장으로 Nadeshiko 미수록 작품 병목이 실제 확인되어 로컬 timed subtitle fallback(POC + 제품 통합, DB schema v3)을 구현했고, 코드 검수 PASS 후 사용자 승인 하에 `main`에 반영 완료됐다.
Task 9에서는 NiceGUI와 pywebview를 실제 Windows probe로 비교해 **NiceGUI(native mode)를 선택**했고, 실제 Nadeshiko 샘플 video_url 자산 20개에서 연속 전환·재생/일시정지·다음/이전·한글/일본어 표시·Windows native 실행·정상 종료 후 프로세스 잔류 없음을 확인한 뒤 선택하지 않은 pywebview 시험 코드를 제거했다. 샘플 20개의 정지 화면 + 음성 관찰은 Nadeshiko 전체 corpus로 일반화하지 않는다.
Task 10에서는 기존 검증 기능만 연결한 **NiceGUI 사용자 화면 5영역**을 구현했고, Windows native E2E(작품 추가/활성화 → 한국어 검색 → corpus-backed 후보 → 장면 검수 → 번역 → 채택 저장 → 종료 → 재실행 → 상태 복원)를 전부 통과해 main에 반영했다. 전체 pytest **117 passed, 15 skipped**.
다음 Task 11에서는 **채택 장면의 MP4 저장과 제작용 JSON/CSV 내보내기, 중복 다운로드 방지**를 구현한다. 새로운 검색·번역 계층은 만들지 않는다.