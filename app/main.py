from query import query_mode

BASE_URL = "https://gokarneshwormun.gov.np/"


def build_answer(query, results):
    if not results:
        return "No relevant information found."

    answer = f"Answer based on municipal data:\n\n"

    for i, (url, content) in enumerate(results, 1):
        answer += f"{i}. {content[:300]}...\n"
        answer += f"   Source: {url}\n\n"

    return answer


def refine_query(q):
    # basic normalization
    return q.strip().lower()


if __name__ == "__main__":
    print("🤖 Municipality Chatbot CLI (type 'exit' to quit)\n")

    while True:
        q = input("Ask: ")

        if q.lower() == "exit":
            break

        q = refine_query(q)

        print("\n🔍 Searching...\n")

        results = query_mode(BASE_URL, q)

        final_answer = build_answer(q, results)

        print("====== ANSWER ======\n")
        print(final_answer)