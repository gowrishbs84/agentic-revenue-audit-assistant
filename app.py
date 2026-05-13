import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


# -----------------------------
# SETUP
# -----------------------------

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="Agentic Revenue Audit Assistant", layout="wide")

st.title("Agentic Revenue Audit Assistant")
st.subheader("LLM Tool Calling + SOP RAG + Workflow Orchestration")


# -----------------------------
# SESSION STATE
# -----------------------------

if "tool_outputs" not in st.session_state:
    st.session_state.tool_outputs = []

if "variance_records" not in st.session_state:
    st.session_state.variance_records = []

if "show_adjustment_module" not in st.session_state:
    st.session_state.show_adjustment_module = False

if "ai_recommendation" not in st.session_state:
    st.session_state.ai_recommendation = ""

if "agent_ran" not in st.session_state:
    st.session_state.agent_ran = False


# -----------------------------
# LOAD DATA
# -----------------------------

sds_df = pd.read_csv("data/sds_ecash.csv")
cmp_df = pd.read_csv("data/cmp_ecash.csv")


# -----------------------------
# TOOL 1: RECONCILIATION TOOL
# -----------------------------

def reconcile_ecash():
    merged_df = pd.merge(
        sds_df,
        cmp_df,
        on=["slot_location", "gamingdt"],
        how="outer",
        suffixes=("_sds", "_cmp")
    )

    merged_df["ecash_in_variance"] = (
        merged_df["ecash_in_sds"] - merged_df["ecash_in_cmp"]
    )

    merged_df["ecash_out_variance"] = (
        merged_df["ecash_out_sds"] - merged_df["ecash_out_cmp"]
    )

    merged_df["variance_status"] = merged_df.apply(
        lambda row: "Variance Found"
        if row["ecash_in_variance"] != 0 or row["ecash_out_variance"] != 0
        else "Matched",
        axis=1
    )

    variance_df = merged_df[
        merged_df["variance_status"] == "Variance Found"
    ]

    return variance_df.to_dict(orient="records")


# -----------------------------
# TOOL 2: SOP RETRIEVAL TOOL
# -----------------------------

def retrieve_sop():
    with open("knowledge_base/ecash_audit_sop.txt", "r", encoding="utf-8") as file:
        return file.read()


# -----------------------------
# TOOL 3: ADJUSTMENT MODULE TOOL
# -----------------------------

def show_adjustment_module():
    return {
        "status": "requested",
        "message": "Human approval adjustment module should be displayed."
    }


# -----------------------------
# OPENAI TOOL DEFINITIONS
# -----------------------------

tools = [
    {
        "type": "function",
        "name": "reconcile_ecash",
        "description": "Compare SDS and CMP eCash data and identify variances.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "retrieve_sop",
        "description": "Retrieve eCash audit SOP guidance.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "show_adjustment_module",
        "description": (
            "Display the human approval adjustment module. Use this tool when the auditor asks to "
        "show adjustments, show adjustment details, list adjustments to be made, post adjustments, "
        "approve adjustments, perform CMP correction, or review adjustment workflow."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    }
]


# -----------------------------
# UI INPUT
# -----------------------------

st.write(
    "Enter an audit request. The LLM agent will decide which tools to call: "
    "reconciliation, SOP retrieval, and adjustment workflow."
)

user_request = st.text_area(
    "Enter auditor request",
    placeholder=(
        "Example: Please reconcile the eCash audit, retrieve the SOP, "
        "and show the adjustment module if human approval is required."
    ),
    height=120
)


# -----------------------------
# RESET BUTTON
# -----------------------------

if st.button("Reset Workflow", key="reset_workflow_button"):
    st.session_state.tool_outputs = []
    st.session_state.variance_records = []
    st.session_state.show_adjustment_module = False
    st.session_state.ai_recommendation = ""
    st.session_state.agent_ran = False
    st.rerun()


# -----------------------------
# RUN AGENT
# -----------------------------

if st.button("Run Agentic Audit Workflow", key="run_agentic_workflow_button"):

    if not user_request.strip():
        st.warning("Please enter an auditor request before running the agent.")
        st.stop()

    st.session_state.tool_outputs = []
    st.session_state.variance_records = []
    st.session_state.show_adjustment_module = False
    st.session_state.ai_recommendation = ""
    st.session_state.agent_ran = True

    st.info("LLM agent is analyzing the auditor request...")

    system_instruction = """
You are an enterprise AI revenue audit agent.

You can use tools to perform the workflow:
1. reconcile_ecash: use this when the auditor asks to reconcile, audit, compare SDS and CMP, identify variance, or review eCash values.
2. retrieve_sop: use this when the auditor asks for SOP, policy guidance, approval rules, audit recommendation, or governance.
3. show_adjustment_module: use this when the auditor asks to show adjustments, show adjustment details, list adjustments to be made, post adjustments, approve adjustments, perform CMP correction, or review adjustment workflow.

Important:
- Do not calculate financial values yourself.
- Use the reconciliation tool for variance detection.
- Use SOP retrieval for audit guidance.
- If the request asks to show or post adjustments after variance/human approval, call show_adjustment_module.
- Final recommendation must be based on tool outputs.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_request}
        ],
        tools=tools
    )

    tool_outputs = []
    latest_variance_records = []
    show_adjustment_module_flag = False

    for item in response.output:
        if item.type == "function_call":
            tool_name = item.name

            st.write(f"LLM selected tool: `{tool_name}`")

            if tool_name == "reconcile_ecash":
                reconcile_result = reconcile_ecash()
                latest_variance_records = reconcile_result

                tool_outputs.append({
                    "tool": "reconcile_ecash",
                    "output": reconcile_result
                })

            elif tool_name == "retrieve_sop":
                sop_result = retrieve_sop()

                tool_outputs.append({
                    "tool": "retrieve_sop",
                    "output": sop_result
                })

            elif tool_name == "show_adjustment_module":
                show_adjustment_module_flag = True
                adjustment_tool_result = show_adjustment_module()

                tool_outputs.append({
                    "tool": "show_adjustment_module",
                    "output": adjustment_tool_result
                })

    if show_adjustment_module_flag and not latest_variance_records:
        latest_variance_records = reconcile_ecash()

        tool_outputs.append({
            "tool": "reconcile_ecash",
            "output": latest_variance_records,
            "note": "Reconciliation executed because adjustment module requires variance records."
        })

    final_prompt = f"""
You are an enterprise AI revenue audit assistant.

The LLM agent selected and executed the following tools.

Tool Outputs:
{json.dumps(tool_outputs, indent=2)}

Tasks:
1. Summarize the reconciliation results.
2. Identify risk level.
3. Recommend the next audit action.
4. Determine if human approval is required.
5. Determine if secondary approval is required for adjustments greater than $100.
6. Explain which tools were called and why.
7. Do not recalculate financial values.

Generate a professional audit recommendation.
"""

    final_response = client.responses.create(
        model="gpt-4.1-mini",
        input=final_prompt
    )

    st.session_state.tool_outputs = tool_outputs
    st.session_state.variance_records = latest_variance_records
    st.session_state.show_adjustment_module = show_adjustment_module_flag
    st.session_state.ai_recommendation = final_response.output_text

    st.rerun()


# -----------------------------
# DISPLAY TOOL OUTPUTS
# -----------------------------

if st.session_state.agent_ran:

    st.subheader("Executed Tool Outputs")

    for output in st.session_state.tool_outputs:
        tool_name = output["tool"]

        st.markdown(f"### Tool: `{tool_name}`")

        if tool_name == "reconcile_ecash":
            records = output["output"]

            if records:
                st.dataframe(pd.DataFrame(records))
            else:
                st.success("No variance found by reconciliation tool.")

        elif tool_name == "retrieve_sop":
            st.text(output["output"])

        elif tool_name == "show_adjustment_module":
            st.info(output["output"]["message"])


# -----------------------------
# DISPLAY AI RECOMMENDATION
# -----------------------------

if st.session_state.ai_recommendation:
    st.subheader("AI Audit Recommendation")
    st.write(st.session_state.ai_recommendation)


# -----------------------------
# ADJUSTMENT MODULE
# -----------------------------

if st.session_state.show_adjustment_module:

    st.subheader("Human Approval Adjustment Module")

    if not st.session_state.variance_records:
        st.success("No variance records available. Adjustment module is not required.")
        st.stop()

    adjustment_df = pd.DataFrame(st.session_state.variance_records)

    st.write(
        "The LLM called the adjustment module tool. "
        "Human approval is required before posting adjustments."
    )

    adjustment_log = []

    for index, row in adjustment_df.iterrows():
        st.markdown("---")
        st.markdown(
            f"### Slot Location: {row['slot_location']} | Gaming Date: {row['gamingdt']}"
        )

        st.write(f"SDS eCash In: ${row['ecash_in_sds']:,.2f}")
        st.write(f"CMP eCash In: ${row['ecash_in_cmp']:,.2f}")
        st.write(f"eCash In Variance: ${row['ecash_in_variance']:,.2f}")

        st.write(f"SDS eCash Out: ${row['ecash_out_sds']:,.2f}")
        st.write(f"CMP eCash Out: ${row['ecash_out_cmp']:,.2f}")
        st.write(f"eCash Out Variance: ${row['ecash_out_variance']:,.2f}")

        approval_status = st.selectbox(
            f"Approval Status for Slot {row['slot_location']}",
            ["Pending Review", "Approved", "Rejected"],
            key=f"approval_status_{index}"
        )

        adjustment_reason = st.text_area(
            f"Adjustment Reason for Slot {row['slot_location']}",
            placeholder="Example: CMP posting delay identified. SDS value verified as source of truth.",
            key=f"adjustment_reason_{index}"
        )

        adjusted_ecash_in_cmp = st.number_input(
            f"Adjusted CMP eCash In for Slot {row['slot_location']}",
            value=float(row["ecash_in_cmp"]),
            key=f"adjusted_in_{index}"
        )

        adjusted_ecash_out_cmp = st.number_input(
            f"Adjusted CMP eCash Out for Slot {row['slot_location']}",
            value=float(row["ecash_out_cmp"]),
            key=f"adjusted_out_{index}"
        )

        adjustment_amount = abs(row["ecash_in_variance"]) + abs(row["ecash_out_variance"])

        secondary_approver = ""

        if adjustment_amount > 100:
            st.warning(
                "Adjustment amount is greater than $100. Secondary approval is required."
            )

            secondary_approver = st.text_input(
                f"Secondary Approver Name for Slot {row['slot_location']}",
                key=f"secondary_approver_{index}"
            )

        adjustment_log.append({
            "slot_location": row["slot_location"],
            "gamingdt": row["gamingdt"],
            "approval_status": approval_status,
            "adjustment_reason": adjustment_reason,
            "original_ecash_in_cmp": row["ecash_in_cmp"],
            "adjusted_ecash_in_cmp": adjusted_ecash_in_cmp,
            "original_ecash_out_cmp": row["ecash_out_cmp"],
            "adjusted_ecash_out_cmp": adjusted_ecash_out_cmp,
            "adjustment_amount": adjustment_amount,
            "secondary_approver": secondary_approver,
            "committed_by": "Revenue Audit User",
            "committed_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    if st.button("Post Approved Adjustments", key="post_approved_adjustments"):
        errors = []

        for item in adjustment_log:

            matching_record = next(
                record for record in st.session_state.variance_records
                if record["slot_location"] == item["slot_location"]
                and record["gamingdt"] == item["gamingdt"]
            )

            if item["approval_status"] != "Approved":
                errors.append(f"Slot {item['slot_location']} is not approved.")

            if not item["adjustment_reason"].strip():
                errors.append(f"Slot {item['slot_location']} requires an adjustment reason.")

            if item["adjustment_amount"] > 100 and not item["secondary_approver"].strip():
                errors.append(
                    f"Slot {item['slot_location']} requires secondary approver because adjustment exceeds $100."
                )

            if item["adjusted_ecash_in_cmp"] != matching_record["ecash_in_sds"]:
                errors.append(f"Slot {item['slot_location']} adjusted CMP eCash In must match SDS.")

            if item["adjusted_ecash_out_cmp"] != matching_record["ecash_out_sds"]:
                errors.append(f"Slot {item['slot_location']} adjusted CMP eCash Out must match SDS.")

        if errors:
            st.error("Adjustment posting failed.")
            for error in errors:
                st.write(f"- {error}")

        else:
            adjustment_log_df = pd.DataFrame(adjustment_log)

            st.success("Approved adjustments posted successfully.")

            st.subheader("Posted Adjustment Log")
            st.dataframe(adjustment_log_df)

            st.download_button(
                label="Download Posted Adjustment Log",
                data=adjustment_log_df.to_csv(index=False).encode("utf-8"),
                file_name="posted_adjustment_log.csv",
                mime="text/csv"
            )