Set up your development environment to use the OpenAI API with an SDK in your preferred language.
This page covers setting up your local development environment to use the OpenAI API. You can use one of our officially supported SDKs, a community library, or your own preferred HTTP client.

Create and export an API key
Before you begin, create an API key in the dashboard, which you'll use to securely access the API. Store the key in a safe location, like a 
.zshrc
file or another text file on your computer. Once you've generated an API key, export it as an environment variable in your terminal.

macOS / Linux
Windows
Export an environment variable on macOS or Linux systems
export OPENAI_API_KEY="your_api_key_here"
OpenAI SDKs are configured to automatically read your API key from the system environment.

Install an official SDK
JavaScript
Python
.NET
Java
Go
To use the OpenAI API in Python, you can use the official OpenAI SDK for Python. Get started by installing the SDK using pip:

Install the OpenAI SDK with pip
pip install openai
With the OpenAI SDK installed, create a file called example.py and copy the example code into it:

Test a basic API request
from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="gpt-5-nano",
    input="Write a one-sentence bedtime story about a unicorn."
)

print(response.output_text)