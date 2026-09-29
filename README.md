# Ring0 — 기억은 말로, 관리는 스킬로

코딩 에이전트가 선호·프로젝트 결정·최근 작업을 다음 세션에서도 꺼내 쓸 수 있게
하는 메모리 스킬입니다. 기본 CLI는 Python 3.9+만 있으면 됩니다.
자동 모드는 OpenCode V2와 서버 PATH의 `python3`, `opencode`를 사용하며,
요약은 OpenCode에 연결된 모델로 실행합니다. 별도 메모리 서버나 pip 설치는 필요 없습니다.

```text
나: 이 프로젝트는 pnpm 써. 기억해줘.
에이전트: 기억했어: 이 프로젝트는 pnpm 사용. (#1)

나: 이 프로젝트 패키지 매니저 뭐 쓰기로 했지?
에이전트: 저장된 결정은 pnpm이야. (#1)
```

## 프로젝트별 자동 설치 — OpenCode V2 / OpenChamber

`/path/to/project`를 **기억을 저장할 프로젝트의 절대 경로**로 바꿔 실행하세요.
OpenCode v2.0.16에서 동작을 확인했습니다.

```bash
git clone https://github.com/RyoTTa/Ring0.git
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

그 프로젝트를 OpenCode/OpenChamber에서 열면 대화 수집·요약·기억 주입이 시작됩니다.
자동화 범위와 기억 저장소는 **설치한 프로젝트별로 분리**됩니다. 상태 확인:

```bash
python3 /path/to/project/.opencode/skills/ring-memory/scripts/automatic.py --root /path/to/project status
```

기존 파일과 내용이 다르면 덮어쓰기 전에 멈춥니다. 업데이트 시 변경 파일을 확인한
뒤 `--force`를 사용하세요. `--dry-run`으로 설치 위치를 미리 볼 수 있습니다.

에이전트에게 설치를 맡길 때는 이 README를 읽고 위 경로에 설치한 다음,
`ring-memory.project` 플러그인이 `active`인지와 `status`의 수집 기록을 확인하도록
요청하세요. 기존 대화가 많으면 최초 수집·요약은 순차적으로 진행됩니다.

요청할 때만 사용하는 기본 스킬은 `--auto`를 빼고 설치하세요.
기본 스킬을 모든 프로젝트에서 쓰려면 `python3 Ring0/scripts/install.py --global`을 사용합니다.
다른 에이전트에서는 이 폴더를 해당 도구의 skills 디렉토리에 `ring-memory`라는
이름으로 복사하면 됩니다. 스킬 이름은 `ring-memory`, 프로젝트 이름은 Ring0입니다.

## 이렇게 쓰세요

자연어로 요청하거나 OpenCode 명령을 사용합니다.

| 요청 | 명령 |
| --- | --- |
| “답변은 짧게 하는 걸 선호해. 기억해줘.” | `/remember 답변은 짧게 하는 걸 선호한다` |
| “지난 배포 결정 찾아줘.” | `/recall 배포` |
| “저장된 기억 상태 보여줘.” | `/rings` |
| “오래된 기억 정리해줘.” | `/dream` |
| “그 선호는 이제 잊어줘.” | 에이전트가 항목을 찾아 보관 처리 |

일반적인 저장 요청은 ring1에 들어갑니다. 사용자가 ring 번호를 정할 필요가 없습니다.
검색은 키워드·접두어 기반이며, 한국어도 지원합니다. 동의어·언어 간 의미 검색은
지원하지 않으므로 에이전트가 관련 키워드로 검색합니다.

## 프로젝트별 자동 기억 (OpenCode V2)

매번 저장을 요청하지 않고 이 프로젝트의 대화·답변·도구 실행 기록을 기억하려면:

```bash
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

기존 설치 업데이트에는 `--force`를 추가합니다. 해당 프로젝트를 OpenCode/OpenChamber에서
열면 플러그인이 자동으로 동작합니다. 다른 프로젝트에는 영향을 주지 않으며,
자동 모드는 `--global`과 함께 설치할 수 없습니다.

1. 기존 프로젝트 세션을 페이지 끝까지 가져오고, 이후 대화와 도구 결과를 수집합니다.
2. 매 모델 호출 전에 ring0 전체와 관련 기억·과거 기록을 컨텍스트에 넣습니다.
3. 응답이 끝나면 새 기록을 ring2로 요약하고, 사용자 발언을 근거로 확인한 사실은 ring1에 저장합니다.
4. 재시작 후에도 저장된 처리 상태에서 이어갑니다. 같은 기록은 중복 저장하지 않습니다.

요약에는 해당 세션의 모델을 사용하므로 추가 모델 호출이 발생합니다. 모델 호출 없이
수집·검색·주입만 사용하려면 프로젝트의 `.opencode/ring-memory.json`에서 `summarize`를
`false`로 설정하세요. `enabled: false`는 자동 처리를 중지합니다.

자동 기록은 `.agent/history.db`, 정리된 기억은 `.agent/rings.db`에 저장됩니다.
스킬이 설치된 **해당 프로젝트 경로** 안의 세션만 처리하며, 별도 Git 저장소인 하위 폴더도
독립 프로젝트로 취급합니다. 자세한 설정과 상태 확인은 [자동 연결 안내](references/hooks.md)에 있습니다.

## 네 개의 ring

| Ring | 용도 | 규칙 |
| --- | --- | --- |
| **0 — kernel** | 핵심 정체성·지속적인 제약 | 사용자 승인 필요, 합계 2,000자, snapshot에 전체 포함 |
| **1 — long-term** | 선호·프로젝트 사실·결정 | 일반 기억의 기본값, 조회로 검색 |
| **2 — episodic** | 최근 결과·세션 요약 | 3회 조회 시 승격, 30일 단위 중요도 감쇠 |
| **3 — scratch** | 임시 작업 메모 | 필요할 때 저장하고 작업이 끝나면 명시적으로 보관 |

`dream`은 중복을 보관하고, 자주 찾는 ring2를 ring1로 올리고, 90일간 사용하지 않은
ring1을 ring2로 내립니다. `pin` 태그는 시간에 따른 감쇠·강등을 막습니다.
반복 실행해도 같은 기간의 감쇠를 중복 적용하지 않습니다. ring0는 자동 정리 대상이 아닙니다.
내용을 물리적으로 삭제하지 않으며, 보관된 항목은 일반 검색에서 빠집니다.

## CLI로 바로 사용

설치 없이 저장소 안에서 실행해도 됩니다.

```bash
python3 scripts/ring.py remember "답변은 짧게 하는 걸 선호한다" --tags preference
python3 scripts/ring.py recall "답변"
python3 scripts/ring.py list
python3 scripts/ring.py snapshot --query "답변"
python3 scripts/ring.py dream --dry-run
```

`--root /path/to/project`로 저장 위치를 지정하세요. 생략하면 가장 가까운 기존
메모리 저장소 또는 Git 루트를 찾고, 둘 다 없으면 현재 디렉토리를 사용합니다.
설치된 스크립트의 위치는 저장 위치에 영향을 주지 않습니다.

ring0를 변경할 때는:

```bash
python3 scripts/ring.py propose "에이전트 이름은 Ring이다"
python3 scripts/ring.py proposals
# 사용자가 해당 제안을 승인한 뒤에만:
python3 scripts/ring.py approve 1
```

기존 `--content`, `--query`, `--id` 문법과 `scripts/dream.py`도 계속 사용할 수 있습니다.
기존 SQLite DB는 처음 열 때 데이터 삭제 없이 필요한 열만 추가합니다.

## 저장·백업

```text
<project>/.agent/
├── rings.db                  # 실제 저장소: 기억·제안·이벤트 이력
└── memory/
    ├── ring0.md … ring3.md   # 활성 기억 전체, 개수 제한 없음
    ├── archive.md            # 보관된 내용
    └── state.json            # 메타데이터·제안·이력까지 포함하는 복원용 백업
```

내용을 변경하면 자동으로 내보냅니다. **SQLite가 원본**이며 Markdown은 열람용입니다.
조회 횟수까지 최신 백업에 반영하려면 `export`를 실행하세요.

```bash
python3 scripts/ring.py export --commit
python3 scripts/ring.py --root /path/to/empty-project restore /path/to/state.json
```

Git 커밋은 `--commit`을 붙일 때만 수행합니다. 무시된 메모리 내보내기 파일도 명시적으로
추가하고, 다른 staged 파일은 커밋에 섞지 않습니다. DB 자체를 Git에 넣지 않습니다.
복원은 빈 저장소에만 적용됩니다. 여러 기기의 동시 DB 병합 기능은 제공하지 않습니다.

`--auto` 없이 설치한 스킬은 요청 기반으로 동작합니다. 자동 모드는 OpenCode V2 전용이고,
다른 호스트는 해당 도구의 이벤트·컨텍스트 훅 연결이 필요합니다.

## 개발

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_automatic.mjs
```

테스트는 저장소 안의 임시 디렉토리를 사용하고 끝나면 삭제합니다.
전체 명령·저장 경로·복원 방법은 [CLI 참고](references/cli.md)에 있습니다.
