# HANDOFF_QUALITY_CHECKLIST.md — active continuation 품질 gate

생성된 handoff를 새 Chat에 넘기기 직전에 검사한다. 모든 필수 항목이 통과해야 quality receipt를 `READY`로 기록한다. 하나라도 실패하면 `NOT_READY`로 남기고 수정 후 전체를 다시 검사한다.

## A. Current truth와 ownership

- [ ] **Q01** Current repository fact를 memory, 이전 대화 또는 추측으로 채우지 않았고 생성 시점에 실제 owner에서 확인했다.
- [ ] **Q02** 생성 시각과 생성 시점의 verified snapshot receipt가 있으며, receipt 형식을 이 framework가 새로 정의하거나 변형하지 않았다.
- [ ] **Q03** snapshot receipt와 SHA를 생성 시점 provenance로만 썼고 새 Chat의 current selector나 영구 current state처럼 고정하지 않았다.
- [ ] **Q04** repository current state·project-level next action·runtime·세부 사실은 해당 owner를 가리키고, conversation-level next action은 owner 사실과 구분돼 handoff가 새 owner처럼 서술되지 않았다.
- [ ] **Q05** ChatGPT Project instruction의 selector, bootstrap, immutable snapshot, freshness, GitHub failure handling 또는 receipt 절차를 복제하지 않았다.
- [ ] **Q06** `PLAYBOOK.md`의 장기 영상 기획 판단 원칙을 복제하거나 대체 owner를 만들지 않았다.
- [ ] **Q07** repository owner의 긴 내용을 무조건 복사하지 않고 continuation에 필요한 source map과 conversation delta만 남겼다.

## B. Decision state와 작업 상태

- [ ] **Q08** current work state와 completed, unresolved, pending이 구분돼 있다.
- [ ] **Q09** pending 실행·응답·검토·렌더 결과를 완료로 기록하지 않았다.
- [ ] **Q10** 최신 accepted decision과 그 판단 이유·범위·결정 주체가 들어 있다.
- [ ] **Q11** rejected 또는 superseded decision과 기각·대체 이유가 들어 있어 과거 안으로 회귀하지 않게 한다.
- [ ] **Q12** open question과 그것을 해결할 evidence 또는 사용자 선택이 구분돼 있다.
- [ ] **Q13** current next action 하나와 why this is next가 명시돼 있다.
- [ ] **Q14** 결과만이 아니라 같은 결정을 재현하는 데 필요한 conversation-specific judgment context가 보존됐다.
- [ ] **Q15** failure root cause, recent correction, regression trap이 실제로 있으면 빠짐없이 기록했고, 없으면 이유와 함께 `None`으로 표시했다.

## C. Provenance와 해석 경계

- [ ] **Q16** `REPO_CURRENT`, `USER_FACT`, `CONVERSATION_DECISION`, `HISTORICAL_EVIDENCE`, `EXTERNAL_RESEARCH`, `AI_INFERENCE`, `PENDING_EXTERNAL`을 구분했다.
- [ ] **Q17** 사용자 실제 피드백과 AI의 원인 해석·권고가 별도 항목이다.
- [ ] **Q18** historical evidence를 current truth로 승격하지 않았다.
- [ ] **Q19** external research에는 source와 확인 시각이 있고, 확인하지 않은 외부 사실을 확인한 것처럼 쓰지 않았다.
- [ ] **Q20** AI inference에는 근거와 불확실성 또는 confidence가 있다.
- [ ] **Q21** repository에 아직 반영되지 않은 대화 결정은 `CONVERSATION_DECISION`으로 표시했고 current owner의 사실처럼 쓰지 않았다.

## D. Continuation 동작과 보안

- [ ] **Q22** handoff의 next action이 자동 실행 명령, 권한 또는 승인으로 해석되지 않게 했다.
- [ ] **Q23** 사용자가 `이어서 진행하자` 등 continuation을 요청하면 current owner와 충돌하지 않는 next action으로 실제 진행할 수 있게 충분히 구체적이다.
- [ ] **Q24** 새 Chat이 handoff 전체를 읽고, repository를 별도 bootstrap하며, 충돌 시 current owner를 우선하도록 적었다.
- [ ] **Q25** 다음 사용자 발화를 이전 Chat의 바로 다음 발화로 취급하고 요청 없는 장황한 recap을 기본 출력하지 않도록 적었다.
- [ ] **Q26** credential, token, secret, private key, session cookie 또는 불필요한 개인정보가 없다.
- [ ] **Q27** 모든 필수 section이 채워졌고 해당 없음은 `None — <이유>`로 명시됐다.
- [ ] **Q28** handoff만으로 새 repository mutation, push, 외부 메시지 또는 다른 권한이 생긴다고 주장하지 않았다.

## Quality receipt 판정

- `READY`: Q01–Q28 모두 통과.
- `NOT_READY`: 하나 이상 실패. 실패 ID와 수정이 필요한 내용을 receipt에 기록한다.

이 receipt는 artifact 구성 품질만 확인한다. Project instruction이 소유하는 bootstrap/freshness receipt, repository owner의 current truth, 외부 작업 완료 증거 또는 결과물 품질 판정을 대신하지 않는다.
