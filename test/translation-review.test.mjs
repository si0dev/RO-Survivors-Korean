import test from 'node:test';
import assert from 'node:assert/strict';
import {loadRecords} from '../tools/records.mjs';

test('reviewed damage and tower descriptions preserve the clarified conditions in the merged data',async()=>{
 const pack=await loadRecords();
 assert.ok(pack.entries["ed118ba8aca6c7cc9c9b2820dba5821bb7af69b0ee656f71132c70ec61031dfb"].ko.includes("화살 1발당 피해량이 기존의 두 배를 넘는 수준으로 증가했습니다(13 → 30)."));
 assert.ok(pack.entries["38188b75840a125c3dc7c6e0ca3ac0e8d6ba44060b6ea140e8786a372d2ec405"].ko.includes("15초마다 몬스터 30마리를 소환하며, 제한 시간 내에 MVP를 처치해야 합니다. 시작 시"));
});

test('Arrow Rain uses one skill name while generic arrow-rain imagery is preserved',async()=>{
 const pack=await loadRecords();
 assert.equal(pack.entries["24642a7fef4e7b7a12c92437152719de83f7e4347b7842b91e3dd3bf0e29423c"].ko,"애로우 레인");
 assert.equal(pack.entries["9fad5941cf3fb008c5074e4be978f8b33202913bc54c0c46697a9022b3ae0ce4"].ko,"화살의 들판: 애로우 레인이 끝나면 화살이 {0}초 동안 지면에 꽂혀 있습니다. 영역을 지나는 적의 이동 속도가 감소하고 {2}초마다 파동 피해량의 {1}%만큼 피해를 받습니다");
 assert.equal(pack.entries["3c1a331ea69c7f116bedd247237bc01fed82cd2286933a44c18b320f7ebd98f1"].ko,"애로우 레인: 피해량이 15% 증가합니다.");
 assert.equal(pack.entries["b6354a0a3575dcdc09dc943a9848f4ab406df9763652c5d95135ca5b430f502e"].ko,"파동 또는 연사 스킬(애로우 샤워, 애로우 레인, 제니 레인 등). 특성, 신 및 엔들리스 타워 강화는 별도 적용");
 assert.equal(pack.entries["1fc2c63fdfe34ffb98b828b0066d9425b582e109bef649285fabf286f21349a7"].ko,"애로우 레인");
 assert.equal(pack.entries["df63382d9a9c52cfe38f097c877bec9476eaf2423add6b36621578870210031f"].ko,"애로우 레인의 신");
 assert.equal(pack.entries["aecd1ad39bf0960b8ee573e77f02f6cc969a509eb2bb5944cd9b450a7e7d5158"].ko,"화살 지대: 애로우 레인이 끝나면 화살이 4초 동안 지면에 꽂혀 남습니다. 범위를 통과하는 적은 둔화되며 0.4초마다 파동 피해량의 50%를 받습니다.");
 assert.equal(pack.entries["994c42f2b691e26ef98312501555605bd4a63417b075ff261d0067dda59df71b"].ko,"화이어 볼트, 콜드볼트, 라이트닝 볼트, 소울 스트라이크, 사이트, 매그넘 브레이크, 소드 댄스, 프로보크, 사기 저하의 함성, 썬더 스톰, 애로우 레인, 민첩성 감소, 팬 오브 나이프, 제니 레인, 회오리차기, 돌려차기, 홍염화(紅炎華), 뇌격, 스프레드 어택, 데스페라도, 그라운드 드리프트, 그랜드 크로스, 메테오 스톰, 화이어 필라, 프로스트 노바, 스톰 가스트, 로드 오브 버밀리온, 헤븐즈 드라이브, 불협화음, 베네딕티오, 마그누스 엑소르시스무스, 기습, 액스 토네이도, 러시 퀘이크, 탐욕, 광석발견, 만월각");
 assert.equal(pack.entries["fc35c202bb42808e4c980bca6bf374d1de39f234c13b57afb60937d7ecea4dd5"].ko,"적 무리 위로 화살비를 내려 밀쳐냅니다.");
});

test('Arrow Repel follows the official Korean Ragnarok skill name',async()=>{
 const pack=await loadRecords();
 assert.equal(pack.entries["2daff804e49b3516507c3a7811fe99f54788c07644b17cc3b20fa0582ce4c5a4"].ko,"챠지 애로우");
 assert.equal(pack.entries["7b545f21efd3f6efd8e474523f0e3ccf53a000eaf53779653438e296226c5cba"].ko,"애로우 샤워, 애로우 레인, 챠지 애로우 중 하나를 시전하면 나머지를 포함한 세 스킬 중 하나를 무작위로 다른 대상에게 무료 시전합니다(미습득 상태에서도 재사용 대기시간을 소모하지 않음).");
 assert.equal(pack.entries["320acaa923b9da919806447f9f2e8da3b12dc934ed760cd2a44c7d5dad7077ad"].ko,"챠지 애로우의 피해량 +{0}%, 사거리 +{1}%.");
 assert.equal(pack.entries["3c377dc699f82ed1ffc68c34b4e35ac968d36caebb87977d1cf5ed60b47f7d85"].ko,"애로우 샤워, 애로우 레인, 챠지 애로우: 자리를 지키며 전장을 화살로 뒤덮습니다.");
 assert.equal(pack.entries["69af85a6387700b782f0abee838b85ed68ac3453afbddca16039739ee08cbec9"].ko,"애로우 샤워, 애로우 레인, 챠지 애로우 및 생존.");
 assert.equal(pack.entries["8621fbb4b4ef4c1c4e3f7583e3aad3deb130687637e32b55dbe3272aca9feab5"].ko,"챠지 애로우가 {0}% 확률로 스턴시킵니다.");
 assert.equal(pack.entries["b6a4b4fd35ec277929105b9e65cdbc72ef4f6505431259e51dc2e9599cd920aa"].ko,"챠지 애로우의 범위 +{0}%, 스턴 확률 {1}%.");
 assert.equal(pack.entries["e431342d3d0acff9308e8f5f2089aa6844a21fd3f07d18d87add7d573b7f508a"].ko,"원거리 기본 공격 및 챠지 애로우. 신, 특성 및 장비는 별도 적용");
 assert.equal(pack.entries["1a9d9b4f2a70f7265e5ce84d6119d3bbc41249d1d7ece428f3aa52e98b4908d6"].ko,"원거리 기본 공격(활, 로드, 악기 등)과 챠지 애로우는 최대");
 assert.equal(pack.entries["b0ab50beb8aaffeef77e12c65cf5349c30413c8b5f22c971d182cb36e4927215"].ko,"챠지 애로우");
 assert.equal(pack.entries["413f779713178e69a20ab5021dbf407ab5a960d754f04d0360ff7d51eca37338"].ko,"챠지 애로우의 신");
 assert.ok(!Object.values(pack.entries).some(entry=>/[애에]로우\s*리[펠팰]/.test(entry.ko)));
});

test('Retreat is consistently named 리트리트 in skill references',async()=>{
 const pack=await loadRecords();
 assert.equal(pack.entries["c701382d437a3bb2f99d321a91dde6a707ac8eab0d53005aa2175e6b395f0858"].ko,"리트리트");
 assert.equal(pack.entries["6e5ca080454b9d150b8de6138d8b60bbbea4429873a74c188380f6a3086738e6"].ko,"기본 공격, 크리티컬, 더블 스트레이핑 및 리트리트.");
 assert.equal(pack.entries["f7d704f49d1d89e2c732586e63470a7f0d92e0fad8d0f1c0d085f8197142017d"].ko,"리트리트");
 assert.equal(pack.entries["7bd7d35d4862b226aac5d4596d166825a2670e8782363525b6523822e5c88444"].ko,"리트리트");
 assert.equal(pack.entries["4967121deca1561cd0079f8e371d5f4b59c5f5ae465eab4c1dcb3aa4a73b70b0"].ko,"리트리트의 신");
 assert.equal(pack.entries["725f903afbc4ece0666bf777300e82f9ae6296b2f320787e7ddc32f27bf7697d"].ko,"신속한 후퇴");
});

test('Caltrops skill is 칼트롭스 while physical traps and Demoralizing Shout retain Korean wording',async()=>{
 const pack=await loadRecords();
 assert.equal(pack.entries["eacb6319639b1bc3b48b3bb1761463c30579e933962b955eb1c66ab0b33ce057"].ko,"칼트롭스");
 assert.equal(pack.entries["29fc24d399c2318b7d303d82cc890cc2a41ba12e5d2ca63f0ecc4e8558a75127"].ko,"하이딩, 쉐도우 스텝 및 칼트롭스: 탈출하고 쓰러지지 않습니다.");
 assert.equal(pack.entries["8f0dec13568c6d53390d2197da00e1ac0d5a30234dc0fd1e6c3e33b9648eab39"].ko,"칼트롭스의 지속시간이 +{0}% 증가합니다.");
 assert.equal(pack.entries["8d7105ccd99655f7454f801c6d5b61653baa9455dfd44b37940b645ce70e0dee"].ko,"쉐도우 스텝이 적 {0}명에게 더 도약합니다(다른 적이 없으면 같은 대상에게 반복). 도약할 때마다 칼트롭스 스킬을 습득하지 않았더라도 도착 지점에 마름쇠 원을 남깁니다. 마지막 도약 후 {2}초 동안 기본 공격이 원래 피해량의 {1}%를 가합니다.");
 assert.equal(pack.entries["8951d5f29caccc2014bf461b1ebdca4acb51603f3248e11cdfb050bc10db4859"].ko,"칼트롭스의 신: 범위가 50% 증가하며, 마름쇠를 밟은 적에게 타격 피해량의 22%에 해당하는 출혈을 부여합니다.");
 assert.equal(pack.entries["d37157ae96f8b74d0e63d1a6342cf091377a3ba640072f748eaa97d1f5d17d9b"].ko,"칼트롭스");
 assert.equal(pack.entries["3dfdbfcaa99c7b9d75a0a8a2aa42b9a826430a31d778905ae4be17ce7ec3435a"].ko,"칼트롭스의 신");
 assert.equal(pack.entries["a2442f377414758090859e93d24b256a66a18b65ea91a9d946c2262513584ccb"].ko,"사기 저하의 함성");
 assert.equal(pack.entries["72feadd6d620ec3e897e4cb9f5f064a0674d007af3c24d8f176c9b9c5e43eb2c"].ko,"마름쇠 +{0}개");
 assert.equal(pack.entries["5bcef99fad9e22490021bba560b88681da9d97435ddbf85388c4092b85fb618b"].ko,"날카로운 마름쇠: 밟은 적에게 출혈을 일으킵니다(초당 피해량 {0})");
 assert.equal(pack.entries["729512c59f3860ff58f908c993eeaa473f3a4d432272fd33b1d3640eb6e812cd"].ko,"코팅된 마름쇠");
 assert.equal(pack.entries["07e9c06c5716911f5aa1be8671d69920200ab44cc3eee4f5eaf6319d7026f164"].ko,"보루: 인듀어가 지속되는 동안 최대 HP의 {0}%에 해당하는 피해를 흡수하는 보호막이 생깁니다. 파괴되거나 종료되면 폭발하여 흡수한 피해를 주변 적에게 돌려주고 사기 저하의 함성과 프로보크를 무료로 시전합니다.");
 assert.equal(pack.entries["13971020535fc8e2fbfe53551f2e04e520b452bf4d099844b2d497c08408cf99"].ko,"마름쇠가 독을 부여합니다: 초당 피해량 {0}.");
 assert.equal(pack.entries["7c6c458bd47932f243fb0a54fe1df65e36af0050e0a7a6bfe161d836ee10b0bb"].ko,"사기 저하의 함성이 적의 피해량을 {0}% 더 감소시킵니다.");
 assert.equal(pack.entries["1cd1cd8576a3b98126f4cfd5357491c59f8c87224ce77f6d3d70873b7a36bdbb"].ko,"자신과 적 사이에 마름쇠를 원형으로 뿌립니다. 밟은 적은 피해를 받고 둔화됩니다.");
 assert.equal(pack.entries["cb91f21758cffdfaf8013c83ad096875c301c9e2f34c663528408574a8e0c2be"].ko,"마름쇠 +1개, 피해량 +15%, 지속시간 증가.");
 assert.equal(pack.entries["bc8cd9a0d5a6c9c2009c78e6bc68385ca19c055369b88b9e6db47b6cc86beb56"].ko,"마름쇠 +{0}개");
 assert.equal(pack.entries["d5e42890a5adff6eeff15b69396453240eac8be2eb74b2c9152a19446eae8daf"].ko,"녹슨 마름쇠");
 assert.equal(pack.entries["e720fcf3adb1a0f8cbd0fd6315cfd19e2a5bc4d9bca59cd722a30a52d98639ec"].ko,"사기 저하의 함성이 적을 {0}초 동안 둔화시킵니다.");
 assert.equal(pack.entries["914bb9be2d2ca415fd3a0541ac487e36cc610743b1c5152f6a57a0ed93be0ec0"].ko,"마름쇠 증가");
 assert.equal(pack.entries["8753c508ffa5d04ab5963b51570c3efa32f88b0ae5f47454d6fd4b560eb6a1a1"].ko,"마름쇠");
 assert.equal(pack.entries["d5a50d70783d1f235e8f87527191ff59da627c43d026bc6b6dc45141f3c48d16"].ko,"마름쇠");
 assert.equal(pack.entries["53db6a64a24e6c17642843239c2751ff676668fd6a4546ee9542ae28280b9c57"].ko,"인듀어의 신: 보루가 폭발하면 사기 저하의 함성과 프로보크도 추가 소모 없이 발동합니다.");
 assert.equal(pack.entries["f3cc616e5dee3c5872e04d80f69cfe3df42a9099582781102a18a28ad51a760a"].ko,"사기 저하의 함성");
 assert.equal(pack.entries["bf381c11c174d8d8f14876e838073439523662f557cd38ba31fe6f841ebdd4c6"].ko,"사기 저하의 함성의 신");
 assert.equal(pack.entries["581b9a2ddecc8e8b470feac122cc6bec0f8b803911be7cc91eee89b075bb0ca8"].ko,"보루: 인듀어가 지속되는 동안 최대 HP의 20%에 해당하는 피해를 돔이 흡수합니다. 파괴되거나 종료되면 폭발해 흡수한 피해를 주변 적에게 돌려주고 사기 저하의 함성과 프로보크를 무료로 발동합니다.");
 assert.equal(pack.entries["5993bfa732a51ccbe85bc25a12915b188655e808f84141767303d5242d00e9f2"].ko,"자신과 적 사이에 마름쇠를 원형으로 뿌립니다. 밟은 적은 피해를 받고 둔화됩니다.");
 assert.equal(pack.entries["994c42f2b691e26ef98312501555605bd4a63417b075ff261d0067dda59df71b"].ko,"화이어 볼트, 콜드볼트, 라이트닝 볼트, 소울 스트라이크, 사이트, 매그넘 브레이크, 소드 댄스, 프로보크, 사기 저하의 함성, 썬더 스톰, 애로우 레인, 민첩성 감소, 팬 오브 나이프, 제니 레인, 회오리차기, 돌려차기, 홍염화(紅炎華), 뇌격, 스프레드 어택, 데스페라도, 그라운드 드리프트, 그랜드 크로스, 메테오 스톰, 화이어 필라, 프로스트 노바, 스톰 가스트, 로드 오브 버밀리온, 헤븐즈 드라이브, 불협화음, 베네딕티오, 마그누스 엑소르시스무스, 기습, 액스 토네이도, 러시 퀘이크, 탐욕, 광석발견, 만월각");
});

test('Approved custom skill names stay consistent throughout the merged data',async()=>{
 const pack=await loadRecords();
 assert.equal(pack.entries["2cba3a6487051accb8f64b114eb794f7f3cc257f20a16f267f7ae3796d7efccc"].ko,"포이즌 밤");
 assert.equal(pack.entries["d932b8b25bc12883c213b0772461412402c588c1b4cf9db1c8f4df04862a02ab"].ko,"쉐도우 스텝");
 assert.equal(pack.entries["64798deeec7b4a6ccf561ea2002682166e9ccaa85b726268eacac8799f2eb5d9"].ko,"소드 댄스");
 assert.equal(pack.entries["dab2ab2718cfc95217ac93d836046e761aaba1db8534930ad210a3df9056b8ff"].ko,"제니 레인");
 assert.equal(pack.entries["6bf163ee6ced9691ab916c74483a867048b875f3f5da71391295d1ed98efec30"].ko,"쉐도우 스텝의 회피율 및 속도 증가 효과가 +{0}% 더 오래 지속됩니다.");
 assert.equal(pack.entries["3fc7172820b3de66cf05b5ad5bcfe4d0bf8e3c46514d52e7b92d961b75a3b036"].ko,"인베넘, 포이즌 밤 및 적 무리를 부식시키는 독.");
 assert.equal(pack.entries["273961e04acec99cdd947fec023a61867d0b4419b8168ff8c8ebd53dcca7e0dd"].ko,"영역에 제니를 비처럼 내립니다. {0}회 파동 중 적에게 처음 적중한 파동이 {1}초 동안 스턴시키고, 모든 파동은 {2}초 동안 적이 받는 매머나이트 피해량을 +{3}% 증가시킵니다. 보스는 스턴 대신 해당 시간 동안 모든 피해를 {4}% 더 받습니다.");
 assert.equal(pack.entries["29fc24d399c2318b7d303d82cc890cc2a41ba12e5d2ca63f0ecc4e8558a75127"].ko,"하이딩, 쉐도우 스텝 및 칼트롭스: 탈출하고 쓰러지지 않습니다.");
 assert.equal(pack.entries["35e235b71ddb22c2e3a897ea333fa8eff23fb415bdeadcb8b502ef980af33cef"].ko,"제니 레인의 표식 지속시간이 {0}초 증가합니다.");
 assert.equal(pack.entries["19587523cccba0294b09f4b88963209e532c78db64c35a65925cad65511dbb41"].ko,"제니 레인으로 표식이 붙은 적은 매머나이트처럼 카트 레볼루션에도 더 큰 피해를 받습니다.");
 assert.equal(pack.entries["2934257a520f4d2b34b56e9194df620a0bebda37cbf62b87372037c12d9d854c"].ko,"쉐도우 스텝 버프 지속 중 피해량 +{0}%, 획득 반경 +{1}m. 사용 후 {2}초 동안 생명력 흡수 {3}%.");
 assert.equal(pack.entries["76bcaa3d181da35787ec0cfdd5983811ce8f8b880b1fa4f01b73547e3a80764e"].ko,"포이즌 밤이 초당 +{0}의 독 피해를 줍니다.");
 assert.equal(pack.entries["79ea10ebfd7a5f5e9e8d44e507e81da9ebf5630e7d06e329cc5aa92885421cc3"].ko,"소드 댄스의 참격이 1회 증가하고 피해량 +{0}%.");
 assert.equal(pack.entries["5c3d539cee4387476115958c8e2c7c2b0f70fa89842b3cf280db54fec97331a8"].ko,"제니 레인이 적 무리 대신 자신에게 떨어집니다. 피해량이 {0}% 감소하고 범위가 {1}% 증가합니다.");
 assert.equal(pack.entries["251936c30c08adbe6a2c0be732a455fe4c304548f28b3a088cf1f62226d63715"].ko,"제니 레인, 노점 개설 및 제니: 돈을 무기로 사용합니다.");
 assert.equal(pack.entries["994776425fe255151f4ebdb4df08938642de0ae56f5ba46059e3148632c61bea"].ko,"소드 댄스: 자신을 중심으로 점점 넓어지는 세 차례의 참격을 가합니다. 가까이 있는 적은 세 차례 모두 피해를 받습니다.");
 assert.equal(pack.entries["b0da67cca60f130a6395ae49decec3ab6e39c991c14677eafc301cdfc964edc1"].ko,"노점 개설의 폭발이 1.2초 동안 스턴시키고 제니 레인처럼 모든 적중 대상에게 매머나이트 표식을 남깁니다.");
 assert.equal(pack.entries["a8fd2bc65eb61cdffcee8345507e7da09790aa9e7c8b6be89e127e67fb1a0280"].ko,"포이즌 밤의 독 지속시간이 {0}초 증가합니다.");
 assert.equal(pack.entries["d5780f122054b8724fd7f1d2b226db8965b3c75bdd773961628843fbb835e7a6"].ko,"소드 댄스 타격에 적중한 적은 {1}초 동안 타격 피해량의 {0}%만큼 출혈 피해를 받습니다.");
 assert.equal(pack.entries["f01386ccd5c7e300d76ef63ee6409a15eeabeae02b10378a07a07f1855854ebf"].ko,"매머나이트가 제니 레인 표식이 붙은 적에게 +{0}% 더 큰 피해를 줍니다.");
 assert.equal(pack.entries["a84b3bb225f5f190fe207a4a8ebe9c3cbb75b1654506be25d5a97482ace88858"].ko,"쉐도우 스텝");
 assert.equal(pack.entries["8d7105ccd99655f7454f801c6d5b61653baa9455dfd44b37940b645ce70e0dee"].ko,"쉐도우 스텝이 적 {0}명에게 더 도약합니다(다른 적이 없으면 같은 대상에게 반복). 도약할 때마다 칼트롭스 스킬을 습득하지 않았더라도 도착 지점에 마름쇠 원을 남깁니다. 마지막 도약 후 {2}초 동안 기본 공격이 원래 피해량의 {1}%를 가합니다.");
 assert.equal(pack.entries["b0c72a77888359f64609f1d28b3e97a98ffe789af883109b30f9850e827b04b2"].ko,"소드 댄스의 신: 충전된 무기가 60%의 추가 번개 피해를 가합니다(랭크당 +5%).");
 assert.equal(pack.entries["e7b2cc271088527e8cd20c18c712af44909705dabf64daabd0a9745b0601fb1f"].ko,"쉐도우 스텝의 신: 그림자 파동이 더 이상 피해를 주지 않습니다. 스턴 효과는 유지됩니다.");
 assert.equal(pack.entries["5883f46c9198f98ebf000f87301839f2f4a797c09e13b8a3b871d6170d26f3e8"].ko,"팬 오브 나이프, 소드 댄스, 애로우 샤워: 부채꼴 공격, 파동, 연사 횟수의 상한(각각 3, 4, 5)이 이제 카드로 얻는 횟수에만 적용됩니다. 타워, 특성, 신 또는 고성방가로 얻는 추가 횟수는 상한과 별도로 적용되며, 상한에 도달해도 사라지지 않습니다. 애로우 샤워는 여전히 레벨 상승으로 얻는 연사 횟수가 5회를 초과할 수 없습니다.");
 assert.equal(pack.entries["e14ddd2d8b338bfe8b8da71c59574fa29951ae6511d7145c982a08ba1b10c81a"].ko,"포이즌 밤: 총 독 피해량이 10% 증가하고 6초 대신 4.5초에 걸쳐 피해를 가합니다. 독구름(포이즌 밤의 신)의 독 피해량도 10% 증가합니다.");
 assert.equal(pack.entries["cb1b63b0ce892df747ddc6cde0e41c2e3f4ede7be7e56e74145d5e514293abdd"].ko,"제니 레인: 피해량이 10%, 범위가 15% 증가합니다.");
 assert.equal(pack.entries["b6354a0a3575dcdc09dc943a9848f4ab406df9763652c5d95135ca5b430f502e"].ko,"파동 또는 연사 스킬(애로우 샤워, 애로우 레인, 제니 레인 등). 특성, 신 및 엔들리스 타워 강화는 별도 적용");
 assert.equal(pack.entries["d466ff5fcba14cc5ed7a12c9179863adfe540f796aabedfa2db8bbb1e1eab8a2"].ko,"소드 댄스");
 assert.equal(pack.entries["a1119b6bced476350c501df1ce1304bd515c4285d0eca19942f5ed461e20bd4c"].ko,"소드 댄스: 자신을 중심으로 점점 넓어지는 세 차례의 참격을 가합니다. 가까이 있는 적은 세 차례 모두 피해를 받습니다.");
 assert.equal(pack.entries["ae4ba69c14b2b13e3095fc8998b6bcef1fd3c9c3f120ef297b502bbc247b99b0"].ko,"소드 댄스의 신");
 assert.equal(pack.entries["a8d3702c1928d7ccd31a77d1e5c8906b6f3a861eceb8ab923259dbe0d242814e"].ko,"소드 댄스가 끝나면 무기에 5초 동안 번개가 충전됩니다. 기본 공격이 60% 추가 번개 피해를 주고 최대 4명의 추가 적에게 전이되며 전이당 피해량이 20% 감소합니다.");
 assert.equal(pack.entries["e045effca65fe7fff8ef6ede1481d5470c8eb272b62a1ac4f6ba4187f8a073a6"].ko,"포이즌 밤");
 assert.equal(pack.entries["ff31fda4edb42e3ac271bbadf8759485413347bb27768548d4e604f49fb6a3f4"].ko,"제니 레인");
 assert.equal(pack.entries["45970acff5f1add82d315381d77722e66928766159d59b43070c055161eec859"].ko,"쉐도우 스텝");
 assert.equal(pack.entries["b72cc4349d3f4117411a377fcb952f62ff002b65e88197df594e461099be1df4"].ko,"포이즌 밤의 신");
 assert.equal(pack.entries["4a33141d059f6a95b21caf04ab209870320d8d0f85860c681347f6360ce1eaec"].ko,"쉐도우 스텝의 신");
 assert.equal(pack.entries["ac4b0b662f4af00d6df871c1831e4fb20f0bacd72790943199c9ad835e30afb6"].ko,"제니 레인의 신");
 assert.equal(pack.entries["994c42f2b691e26ef98312501555605bd4a63417b075ff261d0067dda59df71b"].ko,"화이어 볼트, 콜드볼트, 라이트닝 볼트, 소울 스트라이크, 사이트, 매그넘 브레이크, 소드 댄스, 프로보크, 사기 저하의 함성, 썬더 스톰, 애로우 레인, 민첩성 감소, 팬 오브 나이프, 제니 레인, 회오리차기, 돌려차기, 홍염화(紅炎華), 뇌격, 스프레드 어택, 데스페라도, 그라운드 드리프트, 그랜드 크로스, 메테오 스톰, 화이어 필라, 프로스트 노바, 스톰 가스트, 로드 오브 버밀리온, 헤븐즈 드라이브, 불협화음, 베네딕티오, 마그누스 엑소르시스무스, 기습, 액스 토네이도, 러시 퀘이크, 탐욕, 광석발견, 만월각");
 assert.ok(!Object.values(pack.entries).some(entry=>/검무|독 폭탄|그림자 걸음|제니 비/.test(entry.ko)));
});
