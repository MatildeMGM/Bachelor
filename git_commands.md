# Clone repo
git clone <repo-url>

# Gå ind i repo
cd <repo-navn>

# Opret og skift til ny branch
git checkout -b <branch-navn>

# Lav ændringer...

# Tilføj og commit
git add .
git commit -m "Beskrivelse"

# Hent ændres ændringer ind 
git pull --no-edit
git 
# Push til GitHub
git push origin <branch-n


# Hent main ind i branch 
git fetch origin
git merge origin/main