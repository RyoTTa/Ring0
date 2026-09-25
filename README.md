# Ring0 — 기억은 말로, 관리는 스킬로

코딩 에이전트가 선호·프로젝트 결정·최근 작업을 다음 세션에서도 꺼내 쓸 수 있게
하는 메모리 스킬입니다. Python 3.9+만 있으면 됩니다. 별도 서버, API 키, pip 설치가 없습니다.

```text
나: 이 프로젝트는 pnpm 써. 기억해줘.
에이전트: 기억했어: 이 프로젝트는 pnpm 사용. (#1)

나: 이 프로젝트 패키지 매니저 뭐 쓰기로 했지?
에이전트: 저장된 결정은 pnpm이야. (#1)
```

## OpenCode에 설치

```bash
git clone https://github.com/RyoTTa/Ring0.git
python3 Ring0/scripts/install.py --global
```

모든 프로젝트에서 스킬과 명령을 사용할 수 있습니다. **기억 자체는 프로젝트별로
분리**됩니다. 특정 프로젝트에만 설치하려면:

```bash
python3 Ring0/scripts/install.py --project /path/to/project
```

기존 파일과 내용이 다르면 덮어쓰기 전에 멈춥니다. 업데이트 시 변경 파일을 확인한
뒤 `--force`를 사용하세요. `--dry-run`으로 설치 위치를 미리 볼 수 있습니다.
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

## 자동으로 매 턴 기억하나요?

기본은 요청할 때 실행되는 스킬입니다. 자동 세션 주입을 쓰려면 호스트에서 snapshot을
모델 컨텍스트에 넣는 연결이 필요합니다. 설치기는 스킬과 슬래시 명령을 설치합니다.
자동 실행 설정과 종료 시 요약 흐름은 [hooks 안내](references/hooks.md)를 참고하세요.

## 개발

```bash
python3 -m unittest discover -s tests -v
```

테스트는 저장소 안의 임시 디렉토리를 사용하고 끝나면 삭제합니다.
전체 명령·저장 경로·복원 방법은 [CLI 참고](references/cli.md)에 있습니다.
