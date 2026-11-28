# RO Survivors Korean Patch

[한국어](README.md) | **English**

This is an **unofficial, AI-assisted fan translation patch** for playing [RO Survivors](https://ro-survivors.com/) in Korean.

## Installation

**[Install the Korean patch](https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ro-ko.user.js)**

1. Install the [Tampermonkey](https://www.tampermonkey.net/) browser extension.
2. Open the installation link above and install the patch.
3. Open or refresh the game, then select **한국어 (Korean)** in the in-game language menu.

The patch runs directly in your browser without any separate application.

## What is translated?

- Game menus and on-screen messages
- Skills and talent trees
- Monsters, equipment, and items
- Story and dialogue
- In-game wiki and latest news

The patch prioritizes established terminology from the Korean version of Ragnarok Online. New or changed content following game updates, some dynamic text, and older news may still appear in English.

## Updates

When translations are added or corrected, the patch automatically retrieves the new translation data and applies it the next time you open or refresh the game. Translation-only updates do not display a separate notification or require reinstalling the patch.

New versions of the patch itself can be installed automatically through Tampermonkey. If an automatic update is delayed, click the in-game notice **새로운 한국어 패치가 있습니다. 클릭하여 업데이트해 주세요.** (A new Korean patch is available. Click to update.) to install the new version. The patch does not force a refresh or update during gameplay.

On the main screen, the Korean patch status appears immediately below the game version in the login area. The main screen and talent tree display the patch name/version and status message on separate lines. In the lobby and during combat, a small patch version label is always visible in the lower-right corner and moves above the controller button hints when they appear. Update notices appear below the area name in the lobby or below the timer and Zeny display during combat, as before. They are not displayed on the character selection screen.

| In-game message | Meaning |
| --- | --- |
| 비공식 한국어 패치 / 엔진 v… | Unofficial Korean patch / engine version currently installed. |
| 일부 콘텐츠는 번역이 반영될 때까지 원문으로 표시됩니다. | Some content has not yet been translated into Korean. |
| 🟡 새로운 한국어 패치가 있습니다. 클릭하여 업데이트해 주세요. | A new patch version is available. Click the notice to open the installation screen. |
| 🟢 최신 한국어 패치가 적용되었습니다. | The latest patch has been applied. The notice disappears after five seconds. |
| 🟡 현재 한국어 패치의 최신 상태를 확인할 수 없습니다. | The current translation status could not be verified. |

The update notice remains visible until the patch is applied. After clicking the installation link, the main screen and talent tree display the reminder to refresh after installation and the link to reopen the installer on two separate lines. The lobby and combat screens display the same information on a single line. You can reopen the link even if you cancel installation or close the window. Lobby and combat notifications are supported from v0.4.9 onward. If an earlier version does not update automatically, use the installation link above to update your existing patch.

## About the translation

This patch is based on AI (artificial intelligence) translation. New translations and corrections draw on existing translations and established Korean Ragnarok Online terminology. AI-generated translations may contain mistranslations, unnatural phrasing, or inconsistent terminology, and not every translation has been reviewed by a human. Some content may appear in its original language after game updates.

[View the changelog (Korean)](CHANGELOG.md)

## Usage notice

This project is not affiliated with or officially endorsed by the developers or operators of RO Survivors or the rights holders of Ragnarok Online. All rights to the names, characters, graphics, music, and content of the game and its source material belong to their respective rights holders.

The patch does not bypass game security features or automate gameplay, and it does not distribute the original game code or assets. It has not been confirmed whether the game's operators permit the use of this patch or redistribution of translations. Account restrictions may apply depending on the game's operating policies.

<details>
<summary>Developer information</summary>

Changes to `main` are validated by GitHub Actions. Translation data changes or engine version increases are automatically published to the `translation-data` branch. The engine is published only when its version increases, and the existing release is retained if validation fails. Updates are delivered through GitHub Raw.

- [Build and validation history](https://github.com/si0dev/RO-Survivors-Korean/actions)
- [Build artifacts](https://github.com/si0dev/RO-Survivors-Korean/actions/workflows/ci.yml)
- [Translation data manifest](https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/manifest.json)
- [Translation data JSON](https://raw.githubusercontent.com/si0dev/RO-Survivors-Korean/translation-data/ko.json)

The patch checks for engine and translation updates when opening the game and every hour during gameplay. Translation data is verified using SHA-256 before being cached. If a connection or validation fails, the existing translation is retained. New source text can be automatically collected and compared by manually running the [Extract game translation changes](https://github.com/si0dev/RO-Survivors-Korean/actions/workflows/extract-source.yml) workflow. Original game files are neither stored nor distributed; execution logs contain only new or changed translation work items and inspection results. The [Extract and verify wiki translation](https://github.com/si0dev/RO-Survivors-Korean/actions/workflows/extract-wiki.yml) workflow automatically visits the categories and subtabs of the public wiki and compares source hashes. Separately from English source extraction, it applies the currently built Korean patch to the same categories and subtabs to verify that approved translations appear correctly. It distinguishes new source text from failures to apply existing translations. The game build is checked daily at 11:00 a.m. KST. A full scan is skipped if the build and relevant files match those of the previous successful verification. Changes to the wiki extractor or wiki/shared translation data trigger an immediate check; shared translation runtime changes are evaluated at the next scheduled check. Changes limited to patch status UI or engine version numbers do not trigger immediate wiki verification, and scheduled checks reuse the previous verification results. Manual runs perform a full check regardless of the cache. Extracted data is processed in memory during execution, and only untranslated items, application failures, and inspection results are logged. Approved translations are integrated separately. The status display is inserted after the `#sp-version` element on the main screen.

| Path | Purpose |
| --- | --- |
| `src/core.mjs` | Source extraction, change detection, and placeholder validation |
| `src/session.mjs` | Connection and update state management |
| `src/browser.mjs` | Game integration, caching, and update checks |
| `src/language-adapter.mjs` | Korean language menu and UI translation |
| `translations/catalog.json` | Schema, version, and build metadata for existing parts |
| `translations/common.json` | Verified shared translation values |
| `translations/game-talents-*.json` | Fixed and variable records for the shared game/talent language table |
| `translations/wiki-*.json` | Fixed and variable wiki-specific records |
| `translations/news.json` | Existing news records |
| `tools/` | Extraction, merging, building, and data publishing |
| `test/` | Unit tests |
| `.github/workflows/ci.yml` | Automated validation and publishing |

[Translation data management and restructuring verification (Korean)](docs/translation-structure.md)

Management-record classifications and shared references are resolved only during the build. Published JSON and userscripts contain only records in the existing schema. The shared game/talent language table is not arbitrarily split.

Node.js 22 or later is required.

```sh
npm test
npm run build
```

The build produces `dist/ro-ko.user.js`, `dist/ko.json`, and `dist/manifest.json`.

Keep source extraction files outside the repository or in the Git-ignored `private/` directory.

```sh
node tools/extract.mjs private/ro-survivors-source.json
node tools/import.mjs private/worklist.json NEW_VERSION
```

Only translations reviewed and marked `approved: true` are merged. Terminology reference: [OpenKore kRO tables](https://github.com/OpenKore/openkore/tree/master/tables).

</details>
