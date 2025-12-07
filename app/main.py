from fastapi import FastAPI
app = FastAPI(
    title="Sedi Intelligent Health Assistant",
    description=(
        "Sedi is an AI-based health assistant that provides continuous, personalized care. "
        "It supports multilingual interaction (English base + Persian + Arabic) "
        "and integrates GPT-powered intelligence, adaptive memory, and emotional engagement."
    ),
    version="2.0.1",

)
