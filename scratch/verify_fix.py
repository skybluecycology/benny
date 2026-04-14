from benny.graph.code_analyzer import LANGUAGES, QUERIES
import tree_sitter as ts

def test_queries():
    errors = 0
    for lang_key, query_str in QUERIES.items():
        # Map lang_key to an extension to get a Language object
        # Note: In code_analyzer, LANGUAGES uses extensions as keys
        ext = ".py" if lang_key == "python" else ".ts" if lang_key == "typescript" else ".js"
        lang = LANGUAGES[ext]
        
        try:
            query = lang.query(query_str)
            print(f"PASS: {lang_key} query is valid.")
        except Exception as e:
            print(f"FAIL: {lang_key} query failed! Error: {e}")
            errors += 1
            
    if errors == 0:
        print("\nAll queries are VALID.")
    else:
        print(f"\nFound {errors} errors.")

if __name__ == "__main__":
    test_queries()
