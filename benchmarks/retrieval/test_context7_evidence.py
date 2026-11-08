import json
import unittest

from context7_evidence import grade


class Context7EvidenceGradeTests(unittest.TestCase):
    def answer(self, url="https://github.com/colinhacks/zod/blob/v4.1.12/packages/zod/package.json", fact=True):
        return json.dumps(dict(version="4.1.12", facts=dict(accepts=fact), approach="z.partialRecord",
                               sources=[f"[Pinned source]({url})"], version_evidence="Verified tag 4.1.12"))

    def test_requires_typed_facts_exact_version_and_official_evidence(self):
        spec = dict(package="Zod", version="4.1.12")
        def check(answer):
            return grade(answer, "zod_records", spec, dict(accepts=True))
        self.assertTrue(check(self.answer())["facts"])
        self.assertTrue(check(self.answer())["evidence"])
        self.assertFalse(check(self.answer(fact=1))["facts"])
        self.assertFalse(check(self.answer(url="https://github.com.evil.test/colinhacks/zod/v4.1.12/"))["evidence"])
        self.assertFalse(check(self.answer(url="https://github.com/colinhacks/zod/blob/v4.1.120/source"))["evidence"])
        self.assertFalse(check(self.answer(url="https://github.com/colinhacks/zod/blob/main/source"))["evidence"])
        self.assertFalse(check("not json")["facts"])
        self.assertFalse(check("[]")["facts"])

    def test_historical_fastapi_page_must_be_the_real_official_page(self):
        spec = dict(package="FastAPI", version="0.118.0")
        def check(url):
            answer = json.dumps(dict(version="0.118.0", facts=dict(supported=False), approach="Depends(db)",
                                     sources=[f"[History]({url})"], version_evidence="Checked 0.118.0"))
            return grade(answer, "fastapi_lifetime", spec, dict(supported=False))["evidence"]
        self.assertTrue(check("https://fastapi.tiangolo.com/advanced/advanced-dependencies/#history"))
        self.assertFalse(check("https://github.com/fastapi/fastapi/blob/main/fastapi.tiangolo.com/advanced/advanced-dependencies"))


if __name__ == "__main__":
    unittest.main()
