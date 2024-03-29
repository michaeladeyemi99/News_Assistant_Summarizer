
import os
from openai import OpenAI
from dotenv import load_dotenv
import requests
import time
import json
import streamlit as st

load_dotenv()

default_model = "gpt-3.5-turbo-16k"
news_api_key = os.getenv("NEWS_API_KEY")

def get_news(topic, page_size):
    url = f"https://newsapi.org/v2/everything?q={topic}&pageSize={page_size}&apikey={news_api_key}"
    
    all_contents = []
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        #Chat GPT added this
        all_contents.clear()

        status = data["status"]
        articles = data["articles"]

        for article in articles:
            source = article["source"]["name"]
            author = article["author"]     
            title =  article["title"] 
            description = article["description"]
            url = article["url"]
            content = article["content"]

            title_description = f"""
            Title: {title}
            Author: {author}
            Description: {description}
            Source: {source}
            URL: {url}
            Content: {content}
            """
            all_contents.append(title_description)

        return all_contents
        
    except requests.exceptions.RequestException as e:
        print("Error occured during API Request")
        return []


class News_Assistant:
    # thread_id = None
    # assistant_id = None

    def __init__(self, model:str = default_model) -> None:
        self.client = OpenAI()
        self.thread_id = None
        self.assistant_id = None
        self.summary = None
        self.model = model
        self.run_id = None

        # if News_Assistant.assistant_id:
        #     self.assistant_id = self.client.beta.assistants.retrieve(
        #         assistant_id=News_Assistant.assistant_id
        #     )
        # if News_Assistant.thread_id:
        #     self.thread_id = self.client.beta.threads.retrieve(
        #         thread_id=News_Assistant.thread_id
        #     )

    def create_assistant(self, name, instructions):
        if not self.assistant_id:
            assistant = self.client.beta.assistants.create(
                model= self.model,
                name= name,
                instructions= instructions,
                tools=[
                    {
                        "type":"function",
                        "function":{
                            "name": "get_news",
                            "description": "Summarize the Content of the News articles",
                            "parameters": {
                                "type": "object",
                                "properties":{
                                    "topic":{
                                        "type":"string",
                                        "description":"Write a summary of the News related to the topic given by the User"
                                    },
                                    "page_size":{
                                        "type": "string",
                                        "description":"This is the number of articles the get_news function should have for page_size"
                                    }
                                },
                                "required":["topic"]
                            }
                        }
                    }
                ]
            )
            
            News_Assistant.assistant_id= assistant.id
            self.assistant = assistant
            self.assistant_id = self.assistant.id
        print(f"The Assistant ID is {self.assistant_id}")

    def create_thread(self):
        if not self.thread_id:
            thread = self.client.beta.threads.create()
            
            News_Assistant.thread_id = thread.id
            self.thread = thread
            self.thread_id = self.thread.id
        print(f"The Thread ID is {self.thread_id}")

    def add_message(self, role, content):
        if self.thread_id:
            message = self.client.beta.threads.messages.create(
                thread_id=self.thread_id,
                role=role,
                content=content
            )
            self.message_id = message.id

    def run(self, instructions):
        if self.assistant and self.thread:
            run_assistant = self.client.beta.threads.runs.create(
                model=self.model,
                thread_id=self.thread_id,
                assistant_id=self.assistant_id,
                instructions=instructions
            )
            self.run_id = run_assistant.id
            print(f"The Run is Commencing {self.run_id}")

    def process_message(self):
        if self.thread_id:
            messages = self.client.beta.threads.messages.list(
                thread_id=self.thread_id,
            )
            summary = []
            last_message = messages.data[0]

            role = last_message.role
            content = last_message.content[0].text.value

            summary.append(content)

            self.summary = "\n".join(summary)

            print("Summary is Executed")

    def get_summary(self):
        return self.summary

    def function_call(self, required_actions):
        if not self.run_id:
            return
        tools_outputs = []

        for action in required_actions["tool_calls"]:
            func_name = action["function"]["name"]
            arguments_json = json.loads(action["function"]["arguments"])

            if func_name == "get_news":
                topic = arguments_json["topic"]
                page_size = arguments_json.get("page_size", 3)
                output = get_news(topic, page_size)

                final_str = ""
                for item in output:
                    final_str += "\n".join(item)

                tools_outputs.append(
                    {
                        "tool_call_id": action["id"],
                        "output": final_str
                     }
                )
            else: 
                raise ValueError ("Can't find such function")
            self.client.beta.threads.runs.submit_tool_outputs(
                thread_id=self.thread_id,
                run_id=self.run_id,
                tool_outputs=tools_outputs
            )

    def wait_for_completed(self):
        if self.run_id:
            while True:
                response = self.client.beta.threads.runs.retrieve(
                    run_id=self.run_id,
                    thread_id=self.thread_id
                )
                print(response.status)

                if response.status == "completed":
                    print("Process function about to begin")
                    self.process_message()
                    break
                elif response.status == "requires_action":
                    print("Function is Calling NOW")
                    self.function_call(
                        required_actions = response.required_action.submit_tool_outputs.model_dump()
                        )
                    

def main():
    manager = News_Assistant()
    st.title("News Assistant Summarizer")

    with st.form(key="Input Form"):
        topic = st.text_input("Enter Topic: ")
        page_size = st.text_input("Enter the number of News articles: ")

        submit_button = st.form_submit_button(label="Run News Assistant")

        if submit_button:
            manager.create_assistant(
                name="News Assistant", 
                instructions="You a news summarizer, that after collecting the news from NEWS API, you summarize the content of the news to the user, please ensure the Tile and the URL is present. Make sure the Title is bolded")
            manager.create_thread()
            manager.add_message(role = "user", content=f"Summarize all the news on this content{topic} with the number of articles being {page_size}")

            manager.run(instructions="Summarize the content gotten from the News API and give it to the user. Also add a new line between the Title and Content for each of the articles, and ensure you add URLs to the article so that users can read more info on the site")
            manager.wait_for_completed()
            summary = manager.get_summary()

            st.write(summary)



if __name__ == "__main__":
    main()