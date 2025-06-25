# 🧠 Trivia Battle AI

Un comparateur de modèles d'IA local pour évaluer leurs performances sur des questions de culture générale. Testez et comparez vos modèles Ollama sur des milliers de questions trivia !

## 🎯 Fonctionnalités

- **Comparaison multi-modèles** : Teste plusieurs modèles Ollama simultanément
- **Tests parallèles** : Accélère les comparaisons grâce au multi-threading
- **Questions équitables** : Même ordre de réponses pour tous les modèles
- **Extraction robuste** : Gère différents formats de réponses (A, B, C, D)
- **Rapport détaillé** : Classement, statistiques par difficulté, analyse des biais
- **Mode debug** : Affichage détaillé pour diagnostiquer les problèmes
- **Téléchargeur intégré** : Récupère automatiquement une base de 4600+ questions

## 📋 Prérequis

- **Python 3.7+**
- **Ollama** installé et en cours d'exécution
- **Modèles Ollama** téléchargés (ex: qwen, llama, gemma, mistral)

## 🚀 Installation

1. **Cloner le projet**
```bash
git clone https://github.com/votre-username/trivia_battle-AI.git
cd trivia_battle-AI
```

2. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

3. **Vérifier qu'Ollama fonctionne**
```bash
ollama list
```

## 💾 Obtenir les questions trivia

### Option 1 : Télécharger automatiquement
```bash
python trivia_game.py
```
- Télécharge ~4600 questions depuis Open Trivia Database
- Stratégie adaptative (rapide puis prudent)
- Génère un fichier CSV prêt à utiliser

### Option 2 : Utiliser un fichier existant
Placez votre fichier CSV avec les colonnes :
- `question`
- `correct_answer` 
- `incorrect_answer_1`
- `incorrect_answer_2`
- `incorrect_answer_3`

## 🎮 Utilisation

### Lancement principal
```bash
python AI_reponse.py
```

### Interface interactive

1. **Sélection des modèles**
   - `0` : Tous les modèles
   - `1,2,3` : Modèles spécifiques

2. **Configuration**
   - Nombre de questions par modèle
   - Délai entre questions 
   - Mode de test (parallèle/verbose)

3. **Exécution**
   - Tests en parallèle pour rapidité
   - Suivi en temps réel
   - Sauvegarde automatique des résultats

## 📊 Exemples de résultats

```
🏆 CLASSEMENT FINAL DES MODÈLES
======================================
RANG MODÈLE              PRÉCISION    SCORE    TAILLE
🥇   mistral:latest      78.5%        157/200  3.8GB
🥈   llama3.2:latest     72.0%        144/200  1.9GB  
🥉   gemma3:latest       68.5%        137/200  3.1GB
4.   codellama:7b        45.2%        90/200   3.6GB
5.   qwen3:0.6b          20.0%        40/200   0.5GB
```

## 🔧 Modes de test

### Mode Parallèle (Recommandé)
- Teste plusieurs modèles simultanément
- Plus rapide
- Suivi global des progrès
- Idéal pour comparer 3-5 modèles

### Mode Verbose (Debug)
- Teste un modèle à la fois
- Affiche chaque question et réponse
- Parfait pour diagnostiquer les problèmes
- Voir pourquoi un modèle échoue

## 📁 Fichiers générés

```
model_comparison_summary_YYYYMMDD_HHMMSS.csv   # Résultats par modèle
model_comparison_detailed_YYYYMMDD_HHMMSS.csv  # Toutes les réponses
trivia_complete_4619q_YYYYMMDD_HHMMSS.csv       # Base de questions
trivia_complete_4619q_YYYYMMDD_HHMMSS_stats.txt # Statistiques
```

## ⚙️ Configuration avancée

### Paramètres par modèle
Le code optimise automatiquement :
- **Timeout** : Plus long pour les gros modèles
- **Tokens max** : Adapté à la taille du modèle  
- **Température** : 0.1 pour cohérence

### Extraction des réponses
Gère automatiquement :
- Balises `<think>` (Qwen, DeepSeek)
- Réponses "The answer is A"
- Lettres seules "B"
- Patterns multiples

## 🐛 Résolution de problèmes

### Modèle donne toujours "A"
- Modèle trop petit (0.6B) ou mal configuré
- Essayez un modèle plus gros (3B+)

### Extraction échoue
- Activez le mode verbose pour voir les réponses brutes
- Le modèle ne suit peut-être pas les instructions

### Ollama non accessible
```bash
# Redémarrer Ollama
ollama serve

# Vérifier les modèles
ollama list
```

### Performances lentes
- Réduisez le nombre de questions
- Augmentez le délai entre requêtes
- Utilisez moins de threads parallèles

## 📈 Interprétation des résultats

### Scores typiques
- **80-90%** : Excellent (GPT-4 niveau)
- **70-80%** : Très bon (modèles 7B+ récents)
- **60-70%** : Bon (modèles 3B+ ou 7B anciens)
- **40-60%** : Moyen (connaissances limitées)
- **20-40%** : Faible (modèle trop petit)
- **<20%** : Problème technique ou modèle inadapté

### Analyse par difficulté
Le rapport détaille les performances sur :
- **Easy** : Questions basiques
- **Medium** : Culture générale standard  
- **Hard** : Connaissances spécialisées

## 🤝 Contribution

1. Fork le projet
2. Créez une branche (`git checkout -b feature/amélioration`)
3. Commit (`git commit -am 'Ajoute une fonctionnalité'`)
4. Push (`git push origin feature/amélioration`)
5. Ouvrez une Pull Request

## 📝 Améliorations possibles

- [ ] Support d'autres APIs (Anthropic, OpenAI)
- [ ] Interface web
- [ ] Graphiques de performance
- [ ] Tests par catégorie
- [ ] Sauvegarde en base de données
- [ ] Mode tournoi entre modèles

## 📜 Licence

MIT License - Voir le fichier LICENSE pour les détails.

## 🙏 Remerciements

- [Open Trivia Database](https://opentdb.com/) pour les questions
- [Ollama](https://ollama.ai/) pour les modèles locaux
- Communauté IA open source

## 📞 Support

- **Issues** : Problèmes ou suggestions sur GitHub
- **Discussions** : Questions générales dans les Discussions
- **Wiki** : Documentation détaillée (à venir)

---

🎯 **Objectif** : Trouver le meilleur modèle local pour vos besoins de trivia et culture générale !

💡 **Astuce** : Commencez avec 50 questions sur 3-4 modèles pour avoir un aperçu rapide, puis lancez un test complet sur les plus prometteurs.