import streamlit as st
import os
import sqlite3
from database.db import get_conn, list_opportunities, get_opportunity

BASE = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE, 'database', 'app.db')

st.set_page_config(page_title='Recruiter Call Tracker')

conn = get_conn(DB_PATH)

st.title('Recruiter Call Tracker')

rows = list_opportunities(conn, limit=200)

st.sidebar.header('Filters')
min_salary = st.sidebar.number_input('Min salary', value=0)
query = st.sidebar.text_input('Search company/role')

filtered = []
for r in rows:
    if r.get('salary_min') and r.get('salary_min') < min_salary:
        continue
    if query and query.lower() not in (str(r.get('company') or '') + ' ' + str(r.get('role') or '')).lower():
        continue
    filtered.append(r)

st.metric('Total Opportunities', len(rows))

st.dataframe([{ 'id': r['id'], 'company': r['company'], 'role': r['role'], 'salary_min': r['salary_min'], 'score': r.get('score'), 'status': r.get('status')} for r in filtered])

sel = st.number_input('Open opportunity id', min_value=0, value=0)
if sel:
    opp = get_opportunity(conn, sel)
    if opp:
        st.header(f"{opp.get('company')} — {opp.get('role')}")
        st.write('Score:', opp.get('score'))
        for t in opp.get('transcripts', []):
            st.subheader('Transcript')
            st.write(t.get('transcript'))
            audio_path = t.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                st.audio(audio_path)
    else:
        st.write('Not found')
