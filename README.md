# RO Survivors 한국어 패치

[RO Survivors](https://ro-survivors.com/)를 한국어로 즐길 수 있도록 만든 비공식 팬 번역 패치입니다.

## 한국어 패치 설치

**[한국어 패치 설치하기](https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ro-ko.user.js)**

1. 브라우저에 [Tampermonkey](https://www.tampermonkey.net/) 확장 프로그램을 설치합니다.
2. 위의 한국어 패치 설치 링크를 눌러 설치합니다.
3. 게임에 접속하거나 새로고침한 후, 게임 내 언어 선택 메뉴에서 **한국어**를 선택합니다.

별도 프로그램을 실행할 필요 없이 브라우저에서 바로 이용할 수 있습니다.

## 무엇이 번역되나요?

- 게임 메뉴 및 화면 안내
- 스킬과 특성 트리
- 몬스터, 장비 및 아이템
- 스토리와 대사
- 게임 내 위키 및 최신 소식

한국 라그나로크의 기존 명칭을 우선 사용합니다. 게임 업데이트로 추가되거나 변경된 내용, 일부 동적 문구 및 과거 소식은 영어로 표시될 수 있습니다.

## 업데이트 안내

번역이 추가되거나 수정되면 패치가 자동으로 새 번역을 받아오며, 다음 게임 접속 또는 새로고침 시 적용됩니다. 번역만 변경된 경우에는 별도 알림이 표시되지 않으며, 패치를 다시 설치할 필요도 없습니다.

패치 자체의 새 버전이 나오면 Tampermonkey를 통해 자동으로 업데이트할 수 있습니다. 자동 업데이트가 늦어질 경우 게임 화면에 표시되는 **새 한국어 패치가 있습니다. 업데이트하려면 클릭해 주세요.** 문구를 눌러 새 버전을 설치할 수 있습니다. 게임을 플레이하는 중에는 강제로 새로고침하거나 업데이트하지 않습니다.

메인 화면에서는 로그인 영역의 게임 버전 바로 아래에 한국어 패치 상태가 표시됩니다. 특성 트리 페이지에서도 상태를 확인할 수 있으며, 로비에서는 상단 중앙의 지역 이름 아래, 전투에서는 타이머·제니 표시 아래에 업데이트 안내만 나타납니다. 평소에는 로비와 전투 화면에 아무것도 표시하지 않으며, 캐릭터 선택 화면에서는 표시하지 않습니다.

| 화면에 표시되는 문구 | 의미 |
| --- | --- |
| 비공식 한국어 패치 / 엔진 v… | 현재 설치된 한국어 패치 버전입니다. |
| 🟡 일부 미번역 | 아직 한국어로 번역되지 않은 내용이 있습니다. |
| 🟡 새 한국어 패치가 있습니다. 업데이트하려면 클릭해 주세요. | 새 패치 버전이 있습니다. 문구를 누르면 설치 화면이 열립니다. |
| 🟢 업데이트 완료 | 새 패치가 적용되었습니다. 5초 후 안내가 사라집니다. |
| 🟡 번역 상태 확인 불가 | 현재 번역 상태를 확인하지 못했습니다. |

패치 업데이트 안내는 적용할 때까지 유지됩니다. 로비 및 전투 화면의 안내는 v0.4.9부터 지원합니다. 이전 버전에서 자동 업데이트가 되지 않는 경우 위의 설치 링크로 기존 패치를 갱신할 수 있습니다.

## 번역에 대하여

게임 업데이트에 맞춰 번역을 추가하고 수정하고 있습니다. 모든 화면이 완벽하게 번역되었거나 검수되었다는 의미는 아니며, 일부 번역이 어색하거나 원문으로 표시될 수 있습니다.

[변경 이력 보기](CHANGELOG.md)

## 이용 안내

이 패치는 RO Survivors 개발자 및 운영사, 라그나로크 온라인 권리자와 제휴하거나 공식 승인을 받은 프로젝트가 아닙니다. 게임과 원작의 명칭, 캐릭터, 그래픽, 음악 및 콘텐츠에 대한 권리는 각 권리자에게 있습니다.

게임 보안 기능을 우회하거나 플레이를 자동화하는 기능을 제공하지 않으며, 게임 원본 코드 및 에셋을 배포하지 않습니다. 패치 사용과 번역 재배포에 대한 운영자의 허용 여부는 확인되지 않았으며, 운영 정책에 따라 계정 이용에 제한이 발생할 수 있습니다.

<details>
<summary>개발자용 정보</summary>

`main`의 변경 사항은 GitHub Actions에서 검증하며, 번역 데이터 변경 또는 엔진 버전 증가 시 `translation-data` 브랜치에 자동 배포합니다. 엔진 배포는 버전 증가 시에만 수행하며 검증 실패 시 기존 배포를 유지합니다. 실제 업데이트 경로는 GitHub Raw입니다.

- [빌드 및 검증 기록](https://github.com/si0dev/RO-Survivors-Korean/actions)
- [빌드 아티팩트](https://github.com/si0dev/RO-Survivors-Korean/actions/workflows/ci.yml)
- [번역 데이터 manifest](https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/manifest.json)
- [번역 데이터 JSON](https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ko.json)

게임 접속 및 플레이 중 1시간마다 엔진과 번역 갱신을 확인합니다. 번역 데이터는 SHA-256 무결성을 확인한 뒤 캐시에 저장하며, 연결 또는 검증 실패 시 기존 번역을 유지합니다. 신규 원문은 [Extract game translation changes](https://github.com/si0dev/RO-Survivors-Korean/actions/workflows/extract-source.yml) 워크플로우를 수동 실행하여 자동 수집·대조합니다. 원본 게임 파일은 저장하거나 배포하지 않으며, 실행 로그에는 신규·변경 번역 작업 대상과 검사 결과만 기록됩니다. 위키는 [Extract and verify wiki translation](https://github.com/si0dev/RO-Survivors-Korean/actions/workflows/extract-wiki.yml)에서 공개 위키 화면의 분류 및 하위 탭을 자동 순회하여 원문 해시를 대조합니다. 영어 추출과 별도로 현재 빌드한 한국어 패치를 적용해 같은 분류·하위 탭의 승인 번역 적용 여부를 확인합니다. 신규 원문과 등록된 번역의 적용 실패를 구분합니다. 매일 오전 11시(KST) 게임 빌드를 확인하며 이전 성공 검증의 빌드와 관련 파일이 같으면 전체 순회를 생략합니다. 관련 코드·데이터 변경 또는 수동 실행 시에는 다시 검사합니다. 추출 데이터는 실행 중 메모리에서만 처리하고 미번역·적용 실패 항목과 검사 결과만 로그에 기록합니다. 승인 번역 반영은 별도로 진행합니다. 상태 표시는 메인 화면의 `#sp-version` 요소 뒤에 삽입합니다.

| 경로 | 역할 |
| --- | --- |
| `src/core.mjs` | 원문 추출, 변경 검사 및 변수 검증 |
| `src/session.mjs` | 접속 및 업데이트 상태 관리 |
| `src/browser.mjs` | 게임 연동, 캐시 및 업데이트 확인 |
| `src/language-adapter.mjs` | 한국어 메뉴와 화면 번역 |
| `translations/catalog.json` | 기존 파트의 스키마·버전·빌드 메타데이터 |
| `translations/common.json` | 근거가 확인된 공통 번역값 |
| `translations/game-talents-*.json` | 본편·특성 공용 언어 테이블의 고정형·가변형 레코드 |
| `translations/wiki-*.json` | 위키 전용 고정형·가변형 레코드 |
| `translations/news.json` | 기존 소식형 레코드 |
| `tools/` | 추출, 병합, 빌드 및 데이터 배포 |
| `test/` | 단위 테스트 |
| `.github/workflows/ci.yml` | 자동 검증 및 배포 |

[번역 데이터 관리 및 구조 개편 검증 기록](docs/translation-structure.md)

관리용 레코드의 분류·공통 참조는 빌드에서만 해석합니다. 배포 JSON 및 사용자 스크립트에는 기존 스키마의 레코드만 포함합니다. 기존 본편·특성 공용 언어 테이블은 임의로 나누지 않습니다.

Node.js 22 이상을 사용합니다.

```sh
npm test
npm run build
```

빌드 결과는 `dist/ro-ko.user.js`, `dist/ko.json`, `dist/manifest.json`입니다.

원문 추출 파일은 저장소 외부 또는 Git에서 제외되는 `private/`에 보관합니다.

```sh
node tools/extract.mjs private/ro-survivors-source.json
node tools/import.mjs private/worklist.json NEW_VERSION
```

검토하여 `approved: true`로 지정한 번역만 병합됩니다. 용어 참고 자료: [OpenKore kRO tables](https://github.com/OpenKore/openkore/tree/master/tables).

</details>
