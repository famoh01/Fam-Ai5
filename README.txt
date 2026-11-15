Fam Ai News - Deploy on Render (complete files)
=================================================
Files in this zip (4 files):
  1. index.html          <- website (all-in-one)
  2. server.py           <- run this! (news server)
  3. requirements.txt    <- empty, for build step
  4. README.txt          <- this guide

STEPS ON YOUR PHONE:
1) Unzip this file -> you must see ALL 4 files above
2) Upload ALL 4 files to your GitHub repo
   (Add file -> Upload files -> select all 4)
3) On Render "New Web Service" form, set:
   - Language      : Python 3   (NOT Docker!)
   - Branch        : main
   - Region        : Singapore
   - Build Command : pip install -r requirements.txt
   - Start Command : python3 server.py
   - Instance Type : $0 Free
   - Environment   : (nothing to set)
4) Click "Deploy web service" -> wait 2-3 minutes
   Your site: https://YOUR-PROJECT.onrender.com

Note: free Render sleeps after 15 min without visitors.
First open may take 30-60 seconds to wake up.
