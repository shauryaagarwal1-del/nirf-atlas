"""Ask NIRF (Level 3): turn a typed question into a small JSON plan, check it, and run it with our own code.

The pipeline, one module per step:
  catalog.py   what the language model is told: the columns, categories per year, states, parameters and
               every engine function with its parameters and sample questions (generated from the code);
  llm.py       one function that sends text to the model (Google Gemini by default) and returns its reply;
  planner.py   asks the model for ONLY a JSON plan and checks it (pydantic); one retry with the error;
  resolve.py   turns what people type ("iitb", "TN", "research", "last 3 years") into the data's names;
  executor.py  runs the checked plan with the engines or the Chart Builder. Nothing the model writes is
               ever executed as code, and every number comes from the cleaned master table.
"""
