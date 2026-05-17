# decisions/

Une décision = un fichier `DEC-NNN-slug.md`.

## Pour ajouter une décision

1. Choisir l'ID suivant disponible (regarder l'index dans `../DECISIONS.md`)
2. Créer `DEC-NNN-slug.md` avec ce squelette :

```
DEC-NNN : Titre court
Date : YYYY-MM-DD
Statut : 📝 Proposed | ✅ Accepted | 🔄 In progress | ⛔ Deprecated | 🔁 Superseded by DEC-MMM
Contexte : ...
Alternatives évaluées : ...
Décision : ...
Implémentation : ...
Trade-offs : ...
```

3. Ajouter la ligne correspondante dans le tableau de `../DECISIONS.md`
4. Si la décision en supersede une autre, modifier le statut de l'ancienne en 🔁
