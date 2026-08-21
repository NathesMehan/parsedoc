import requests

def query_ollama(prompt: str, model: str = "llama3.2") -> str:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        }
    )

    #Raise error if request fails
    response.raise_for_status()
    data = response.json()
    return data["response"]

if __name__ == "__main__":
    result = query_ollama("Say hello in one sentence.")
    print(result)