- An LLM is a machine learning model trained on vast amounts of text data to understand, summarize, generate and predict content.
- Chain-Of-Thought (CoT) is a technique to guide an LLM's reasoning process by breaking down complex problems into smaller, manageable steps, allowing the model to generate more accurate and coherent responses.
- ReAct (Reason + Act) is a framework that enables an LLM to use tools and take actions in a structured manner, combining reasoning and action to solve problems effectively.

## What is an AI Agent?

- At its core, an AI agent is an intelligent system capable of perceiving its environment, making decisions, and taking actions to achieve specific goals.
- Key characteristics include autonomy, adaptability and interaction with its surroundings.
- Instead of merely assisting you, AI agents work alongside you or independently on your behalf. They can handle a range of tasks, from simple responses to more complicated multi-step assignments

### Components of an AI Agent

- LLM: serves as the brain
- Tools: external functions, APIs, or resources that the agent can access and utilize.
- Instructions: guidelines or prompts that direct the agent's behavior.
- Memory: stores information about past interactions and experiences.
- Runtime/Orchestration Layer: manages the execution of tasks and coordinates the agent's activities.

### Prompting

- Prompting is the means by which LLMs are programmed or guided.
- A prompt is a set of instructions or context provided to the LLM

### Role-Based Prompting

- This is about giving your LLM a specific identity or "persona" to inhabit, which can influence its responses and behavior.
- When working with an LLM’s API, we’ll normally specify a system prompt for general instructions. If using an LLM app like ChatGPT, you typically combine system and user prompts.

### Evaluating LLMs

- Evaluation is crucial to ensure that the LLM performs as expected and meets the desired objectives.
  - Ground Truth Evaluation: Comparing the LLM's output against a known correct answer or benchmark, for structured data: check formatting/structure, completeness, and accuracy. For unstructured data: use human evaluation and use another LLM to evaluate the output(LLM-as-a-judge). It is also important to evaluate the evaluator
  - Consistency & Persona Adherence: Is the agent staying within its defined role?
  - Robustness Testing: Assess resilience against adversarial attacks. This is critical if the agent handles sensitive information or could cause harm.
  - Simple Metrics: Easy-to-implement measures like median response length are good for evaluating and monitoring language models for improved usability and cost efficiency.
