import sys
sys.path.insert(0, r'D:\AIProjects\ResearchReader\researchreader')
from dictionary import ResearchDictionary

d = ResearchDictionary()
passed = 0
failed = 0
results = []

def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        results.append(f'  PASS  {name}')
    else:
        failed += 1
        results.append(f'  FAIL  {name}')

# 1. Exact alias lookup
r = d.normalize('英伟达')
check('exact alias lookup (zh)', len(r) == 1 and r[0]['canonical'] == 'NVIDIA' and r[0]['matched_alias'] == '英伟达')

# 2. Canonical lookup
r = d.normalize('Tesla')
check('canonical as query', len(r) == 0)

# 3. Missing entity
r = d.normalize('NonExistent')
check('missing entity returns empty', len(r) == 0)

# 4. Case sensitivity
r1 = d.normalize('Nvidia')
r2 = d.normalize('nvidia')
check('case sensitive: "Nvidia" matches', len(r1) == 1)
check('case sensitive: "nvidia" does NOT match', len(r2) == 0)

# 5. Metadata accessible
r = d.normalize('英伟达')
meta = r[0]['entity'].metadata
check('metadata has ticker', meta.get('ticker') == 'NVDA')
check('metadata has sector', meta.get('sector') == 'Technology')

# 6. Loaded entity count
check('loaded 6 entities', len(d._entities) == 6)
check('alias map has 17 entries', len(d._alias_map) == 17)

print('=== Dictionary Test Results ===')
for line in results:
    print(line)
print()
print(f'Results: {passed} passed, {failed} failed, {passed + failed} total')
if failed == 0:
    print('ALL TESTS PASSED')
else:
    print('SOME TESTS FAILED')
    sys.exit(1)
