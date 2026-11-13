import os
import json
import code

from dotenv import load_dotenv
load_dotenv()

# OpenAI SDK
from openai import OpenAI


# =========================================================
# CREATE OPENAI CLIENT
# =========================================================
#
# This creates the SDK client object that lets us talk
# to OpenAI models.
#
# It automatically uses the API key stored in:
#
# export OPENAI_API_KEY="your_key_here"
#
# or in a .env setup if you use one.
#
# Every model call will go through this client.
#
# =========================================================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


# =========================================================
# TOOL DEFINITIONS
# =========================================================
#
# These are NOT actual Python functions yet.
#
# This is a SCHEMA / DESCRIPTION given to the LLM.
#
# You are telling the model:
#
# "Hey, you are allowed to call a tool named
# get_weather and here is how it works."
#
# The model reads this and decides whether
# it wants to use the tool.
#
# This is similar to:
#
# - function calling
# - MCP tool definitions
# - structured tool APIs
#
# The model NEVER executes Python directly.
# It ONLY requests tool usage.
#
# =========================================================
TOOLS = [
    {
        "type": "function",

        "function": {

            # Tool name the model can invoke
            "name": "get_weather",

            # Natural language explanation for the model
            "description": "Get weather for a city",

            # JSON schema describing arguments
            "parameters": {

                "type": "object",

                "properties": {

                    # Tool argument:
                    # city="Mumbai"
                    "city": {
                        "type": "string",
                        "description": "City name"
                    }
                },

                # Model MUST provide this argument
                "required": ["city"]
            }
        }
    }
]


# =========================================================
# REAL PYTHON TOOL EXECUTION
# =========================================================
#
# This is YOUR ACTUAL TOOL.
#
# The LLM never directly runs this.
#
# Instead:
#
# 1. LLM REQUESTS TOOL CALL
# 2. YOUR AGENT EXECUTES TOOL
# 3. RESULT IS SENT BACK TO MODEL
#
# IMPORTANT:
#
# This layer is fully controlled by YOU.
#
# Here you can:
#
# - call APIs
# - query databases
# - use MCP tools
# - access files
# - run shell commands
# - call other agents
#
# =========================================================
def call_tool(tool_name, arguments):

    """
    Executes the requested tool.
    """

    # Example tool routing
    if tool_name == "get_weather":

        # Extract tool arguments
        city = arguments["city"]

        # Fake weather response
        #
        # Normally this would call:
        #
        # - weather API
        # - external service
        # - database
        #
        return f"The weather in {city} is 28°C and sunny."

    # Safety check
    raise ValueError(f"Unknown tool: {tool_name}")


# =========================================================
# LLM CALL FUNCTION
# =========================================================
#
# This function sends the FULL conversation
# to the model.
#
# The model then decides:
#
# OPTION 1:
# - answer normally
#
# OPTION 2:
# - request a tool call
#
# The returned object is NOT plain text.
#
# It is a structured SDK response object.
#
# =========================================================
def call_llm(conversation):

    response = client.chat.completions.create(

        # Model to use
        model="gpt-5",

        # Full running conversation history
        messages=conversation,

        # Tool definitions exposed to model
        tools=TOOLS,

        # Allow model to decide whether to use tools
        tool_choice="auto"
    )

    # Return assistant message only
    return response.choices[0].message


# =========================================================
# MAIN AGENT LOOP
# =========================================================
#
# This is the actual "agent".
#
# Why is it a LOOP?
#
# Because the model may:
#
# 1. call tool
# 2. receive tool result
# 3. call another tool
# 4. think again
# 5. finally answer
#
# So the loop continues until:
#
# - no more tool calls exist
#
# Then we return final answer.
#
# =========================================================
def agent_loop(user_query):

    # =========================================
    # INITIAL CONVERSATION STATE
    # =========================================
    #
    # Conversation history is stored as a list.
    #
    # This becomes the model context.
    #
    # Every iteration grows this list.
    #
    # =========================================
    conversation = [
        {
            "role": "user",
            "content": user_query
        }
    ]

    # Infinite loop until final answer
    while True:

        # =====================================
        # CALL THE MODEL
        # =====================================
        #
        # Model sees:
        #
        # - conversation
        # - available tools
        #
        # Then returns either:
        #
        # - normal text
        # - tool call request
        #
        # =====================================
        llm_message = call_llm(conversation)

        # =====================================
        # DEBUGGING / INSPECTION BREAKPOINT
        # =====================================
        #
        # code.interact opens an interactive
        # Python shell.
        #
        # VERY IMPORTANT FOR AGENT DEBUGGING.
        #
        # You can inspect:
        #
        # - llm_message
        # - tool_calls
        # - conversation
        # - arguments
        #
        # Example:
        #
        # >>> llm_message.tool_calls
        #
        # >>> conversation
        #
        # >>> llm_message.content
        #
        # This is EXTREMELY useful when
        # building agents.
        #
        # =====================================
        code.interact(local=locals())

        # =====================================
        # STORE ASSISTANT MESSAGE
        # =====================================
        #
        # IMPORTANT:
        #
        # Even tool call requests must be added
        # to conversation history.
        #
        # Otherwise the model loses context.
        #
        # =====================================
        conversation.append(llm_message)

        # =====================================
        # TOOL CALL PATH
        # =====================================
        #
        # If tool_calls exists:
        #
        # - model wants tools
        #
        # Example:
        #
        # "Call get_weather(city='Mumbai')"
        #
        # =====================================
        if llm_message.tool_calls:

            # Model may request MULTIPLE tools
            for tool_call in llm_message.tool_calls:

                # Tool name requested by model
                tool_name = tool_call.function.name

                # Arguments arrive as JSON STRING
                #
                # Example:
                #
                # '{"city":"Mumbai"}'
                #
                # We convert into Python dict.
                #
                arguments = json.loads(
                    tool_call.function.arguments
                )

                # =================================
                # EXECUTE REAL TOOL
                # =================================
                #
                # This is where your external
                # systems are actually called.
                #
                # =================================
                result = call_tool(
                    tool_name,
                    arguments
                )

                # =================================
                # SEND TOOL RESULT BACK TO MODEL
                # =================================
                #
                # CRITICAL STEP.
                #
                # Without this, the model never
                # sees tool output.
                #
                # The model now reasons over:
                #
                # "Weather in Mumbai is sunny"
                #
                # =================================
                conversation.append(
                    {
                        "role": "tool",

                        # Links result back to
                        # specific tool call
                        "tool_call_id": tool_call.id,

                        # Actual tool output
                        "content": result
                    }
                )

        # =====================================
        # FINAL ANSWER PATH
        # =====================================
        #
        # No tool calls means:
        #
        # Model is done reasoning.
        #
        # Return final answer to user.
        #
        # =====================================
        else:
            return llm_message.content


# =========================================================
# SCRIPT ENTRY POINT
# =========================================================
#
# This only runs if the file itself
# is executed directly.
#
# Example:
#
# python agent.py
#
# =========================================================
if __name__ == "__main__":

    # Start agent loop
    answer = agent_loop(
        "What's the weather in Mumbai?"
    )

    # Print final answer
    print("\nFINAL ANSWER:\n")
    print(answer)