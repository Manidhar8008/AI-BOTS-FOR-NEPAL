from query import query_mode

BASE_URL = "https://gokarneshwormun.gov.np/"

if __name__ == "__main__":
    print("🤖 Municipality Chatbot CLI (type 'exit' to quit)\n")

    while True:
        q = input("Ask: ")

        if q.lower() == "exit":
            break

        results = query_mode(BASE_URL, q)

        print("\n====== ANSWERS ======")

        if not results:
            print("❌ No results found")

        for url, content in results:
            print(f"\n🔗 {url}\n{content[:400]}")