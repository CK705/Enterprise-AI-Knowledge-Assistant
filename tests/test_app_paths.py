import unittest
from pathlib import Path

import main
from langchain_core.documents import Document


class AppPathConfigTests(unittest.TestCase):
    def test_storage_paths_are_inside_workspace(self):
        base_dir = Path(main.__file__).resolve().parent
        for path_name in ("STORAGE_DIR", "DB_DIR"):
            value = Path(getattr(main, path_name)).resolve()
            self.assertTrue(
                value.is_relative_to(base_dir),
                f"{path_name} should live inside the project directory: {value}",
            )

    def test_role_filtering_is_disabled_for_pipeline_access(self):
        docs = [Document(page_content="A", metadata={"allowed_roles": ["Manager"]})]
        self.assertEqual(main.filter_docs_by_role(docs, "Employee"), docs)


if __name__ == "__main__":
    unittest.main()
