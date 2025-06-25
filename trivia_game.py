import requests
import html
import time
from datetime import datetime
import os
import json
import csv

class OptimizedTriviaDownloader:
    def __init__(self):
        self.base_url = "https://opentdb.com/api.php"
        self.session_token = None
        self.last_request_time = None
        self.total_target = 4620  # Nombre réel de questions disponibles
        self.MAX_DANGER = 4520    # Seuil de prudence - passer en mode lent
        self.enable_backups = False  # Par défaut, pas de sauvegardes intermédiaires
        
    def get_adaptive_batch_size(self, current_count):
        """Retourne la taille de lot adaptée selon le nombre de questions"""
        if current_count < self.MAX_DANGER:
            return 50  # Mode rapide
        else:
            return 10  # Mode prudent pour les dernières questions
    
    def get_adaptive_delay(self, current_count):
        """Retourne le délai adapté selon le nombre de questions"""
        if current_count < self.MAX_DANGER:
            return 5.2  # Délai normal
        else:
            return 8.0  # Délai plus long pour la fin
        
    def wait_for_rate_limit(self, current_count=0):
        """Attente adaptative selon le nombre de questions"""
        if self.last_request_time:
            adaptive_delay = self.get_adaptive_delay(current_count)
            elapsed = time.time() - self.last_request_time
            
            if elapsed < adaptive_delay:
                wait_time = adaptive_delay - elapsed
                mode = "PRUDENT" if current_count >= self.MAX_DANGER else "RAPIDE"
                print(f"⏳ {wait_time:.1f}s [{mode}]", end=" ", flush=True)
                time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def get_session_token(self, current_count=0):
        """Récupère un token de session"""
        try:
            self.wait_for_rate_limit(current_count)
            response = requests.get("https://opentdb.com/api_token.php?command=request", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data['response_code'] == 0:
                    self.session_token = data['token']
                    print(f"✅ Token: {self.session_token[:8]}...")
                    return True
            return False
        except:
            return False
    
    def reset_token(self, current_count=0):
        """Reset le token quand épuisé"""
        if self.session_token:
            try:
                self.wait_for_rate_limit(current_count)
                url = f"https://opentdb.com/api_token.php?command=reset&token={self.session_token}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    print("🔄 Token reset")
                    return True
            except:
                pass
        return False
    
    def get_questions_batch(self, amount=50, category=None, current_count=0):
        """Récupère un lot de questions avec taille adaptative"""
        # Ajuster la taille selon le seuil
        adaptive_amount = min(amount, self.get_adaptive_batch_size(current_count))
        
        params = {'amount': adaptive_amount}
        
        if category:
            params['category'] = category
        if self.session_token:
            params['token'] = self.session_token
        
        try:
            self.wait_for_rate_limit(current_count)
            response = requests.get(self.base_url, params=params, timeout=15)
            
            if response.status_code == 429:
                return [], 'rate_limit'
            elif response.status_code == 200:
                data = response.json()
                
                if data['response_code'] == 0:
                    return data['results'], 'success'
                elif data['response_code'] == 1:
                    return [], 'no_results'
                elif data['response_code'] == 4:
                    return [], 'token_empty'
                elif data['response_code'] == 5:
                    return [], 'rate_limit'
                else:
                    return [], f'error_{data["response_code"]}'
            else:
                return [], f'http_{response.status_code}'
                
        except Exception as e:
            return [], 'exception'
    
    def download_all_4620(self):
        """Télécharge les 4620 questions disponibles avec stratégie adaptative"""
        print("🎯 TÉLÉCHARGEMENT ADAPTATIF DES 4620 QUESTIONS")
        print("="*60)
        print(f"📊 Stratégie: RAPIDE jusqu'à {self.MAX_DANGER}, puis PRUDENT")
        print(f"🚀 Mode RAPIDE: 50 questions/lot, délai 5.2s")
        print(f"🐌 Mode PRUDENT: 10 questions/lot, délai 8.0s")
        print("💾 UN SEUL fichier CSV final (pas de backups intermédiaires)")
        
        # Obtenir le token
        if not self.get_session_token():
            print("⚠️ Pas de token - risque de doublons")
        
        all_questions = []
        unique_questions = set()  # Pour éviter les doublons
        consecutive_empty = 0
        batch_number = 1
        
        start_time = time.time()
        
        print(f"📥 Objectif: {self.total_target} questions")
        print("🚀 Démarrage du téléchargement...")
        
        while len(all_questions) < self.total_target and consecutive_empty < 15:
            current_count = len(all_questions)
            
            # Déterminer le mode actuel
            if current_count < self.MAX_DANGER:
                mode_icon = "🚀"
                mode_text = "RAPIDE"
                batch_size = 50
            else:
                mode_icon = "🐌"
                mode_text = "PRUDENT"
                batch_size = 10
            
            # Affichage avec barre de progression
            elapsed = time.time() - start_time
            questions_per_min = (current_count / elapsed) * 60 if elapsed > 0 else 0
            eta_minutes = (self.total_target - current_count) / questions_per_min if questions_per_min > 0 else 0
            
            # Barre de progression
            progress_bar = self.create_progress_bar(current_count, self.total_target)
            
            print(f"\r{mode_icon} {progress_bar} | "
                  f"{current_count:4d}/{self.total_target} | "
                  f"{questions_per_min:4.1f}/min | ETA:{eta_minutes:4.0f}min | [{mode_text}]", end="", flush=True)
            
            questions, status = self.get_questions_batch(batch_size, current_count=current_count)
            
            if status == 'success' and questions:
                new_count = 0
                for q in questions:
                    # Utiliser question + réponse comme clé unique
                    question_text = html.unescape(q['question'])
                    answer_text = html.unescape(q['correct_answer'])
                    unique_key = f"{question_text}|{answer_text}"
                    
                    if unique_key not in unique_questions:
                        unique_questions.add(unique_key)
                        all_questions.append(q)
                        new_count += 1
                
                if new_count > 0:
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                
                # Affichage d'étapes importantes (sans sauvegarde)
                if len(all_questions) % 1000 == 0 and len(all_questions) > 0:
                    print(f"\n🎯 Étape: {len(all_questions)} questions récupérées")
                    
                # Optionnel: sauvegarde de sécurité seulement si activée
                if self.enable_backups:
                    save_interval = 250 if current_count >= self.MAX_DANGER else 500
                    if len(all_questions) % save_interval == 0 and len(all_questions) > 0:
                        print(f"\n💾 Sauvegarde sécurité à {len(all_questions)} questions...")
                        self.save_progress_csv(all_questions, f"backup_{len(all_questions)}")
                    
            elif status == 'token_empty':
                print(f"\n🔄 Token épuisé (lot {batch_number})...")
                if self.reset_token(current_count):
                    consecutive_empty = 0
                    continue
                else:
                    # Obtenir un nouveau token
                    self.session_token = None
                    if self.get_session_token(current_count):
                        consecutive_empty = 0
                        continue
                    else:
                        consecutive_empty += 1
                        
            elif status == 'rate_limit':
                print(f"\n⏳ Rate limit - pause adaptative...")
                pause_time = 60 if current_count >= self.MAX_DANGER else 30
                time.sleep(pause_time)
                consecutive_empty += 1
                
            elif status == 'no_results':
                print(f"\n📭 Plus de résultats (lot {batch_number})")
                consecutive_empty += 1
                
            else:
                consecutive_empty += 1
                
            batch_number += 1
            
            # Pause de maintenance plus fréquente près de la fin
            maintenance_interval = 50 if current_count >= self.MAX_DANGER else 100
            if batch_number % maintenance_interval == 0:
                pause_time = 60 if current_count >= self.MAX_DANGER else 30
                print(f"\n☕ Pause maintenance ({pause_time}s)...")
                time.sleep(pause_time)
        
        print(f"\n\n✅ TÉLÉCHARGEMENT TERMINÉ!")
        print(f"📊 Questions récupérées: {len(all_questions)}")
        print(f"⏱️ Temps total: {(time.time() - start_time)/60:.1f} minutes")
        print(f"📈 Couverture: {(len(all_questions)/self.total_target)*100:.1f}%")
        
        if len(all_questions) >= self.MAX_DANGER:
            print(f"🎯 Mode PRUDENT activé après {self.MAX_DANGER} questions")
        
        return all_questions
    
    def save_to_csv(self, questions, filename=None):
        """Sauvegarde les questions en format CSV"""
        if not questions:
            return None
            
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trivia_database_{len(questions)}q_{timestamp}.csv"
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'id',
                    'category', 
                    'type',
                    'difficulty',
                    'question',
                    'correct_answer',
                    'incorrect_answer_1',
                    'incorrect_answer_2', 
                    'incorrect_answer_3',
                    'all_answers_shuffled'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, q in enumerate(questions, 1):
                    # Décoder le HTML
                    question = html.unescape(q['question'])
                    correct_answer = html.unescape(q['correct_answer'])
                    incorrect_answers = [html.unescape(ans) for ans in q['incorrect_answers']]
                    
                    # Créer toutes les réponses mélangées
                    all_answers = [correct_answer] + incorrect_answers
                    import random
                    shuffled_answers = all_answers.copy()
                    random.shuffle(shuffled_answers)
                    
                    # Préparer la ligne CSV
                    row = {
                        'id': i,
                        'category': q['category'],
                        'type': q['type'],
                        'difficulty': q['difficulty'],
                        'question': question,
                        'correct_answer': correct_answer,
                        'incorrect_answer_1': incorrect_answers[0] if len(incorrect_answers) > 0 else '',
                        'incorrect_answer_2': incorrect_answers[1] if len(incorrect_answers) > 1 else '',
                        'incorrect_answer_3': incorrect_answers[2] if len(incorrect_answers) > 2 else '',
                        'all_answers_shuffled': ' | '.join(shuffled_answers)
                    }
                    
                    writer.writerow(row)
                    
                    # Progress indicator
                    if i % 1000 == 0:
                        print(f"📝 CSV: {i}/{len(questions)} lignes écrites...")
            
            print(f"\n📊 FICHIER CSV CRÉÉ: {filename}")
            print(f"📁 Taille: {os.path.getsize(filename)/1024/1024:.2f} MB")
            print(f"📋 Format: {len(questions)} lignes x {len(fieldnames)} colonnes")
            
            return filename
            
        except Exception as e:
            print(f"❌ Erreur création CSV: {e}")
            return None

    def save_progress_csv(self, questions, prefix="progress"):
        """Sauvegarde de progression en CSV"""
        try:
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{prefix}_{len(questions)}q_{timestamp}.csv"
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'id', 'category', 'type', 'difficulty', 'question', 'correct_answer',
                    'incorrect_answer_1', 'incorrect_answer_2', 'incorrect_answer_3', 'all_answers_shuffled'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, q in enumerate(questions, 1):
                    question = html.unescape(q['question'])
                    correct_answer = html.unescape(q['correct_answer'])
                    incorrect_answers = [html.unescape(ans) for ans in q['incorrect_answers']]
                    
                    # Créer toutes les réponses mélangées
                    all_answers = [correct_answer] + incorrect_answers
                    import random
                    shuffled_answers = all_answers.copy()
                    random.shuffle(shuffled_answers)
                    
                    row = {
                        'id': i,
                        'category': q['category'],
                        'type': q['type'],
                        'difficulty': q['difficulty'],
                        'question': question,
                        'correct_answer': correct_answer,
                        'incorrect_answer_1': incorrect_answers[0] if len(incorrect_answers) > 0 else '',
                        'incorrect_answer_2': incorrect_answers[1] if len(incorrect_answers) > 1 else '',
                        'incorrect_answer_3': incorrect_answers[2] if len(incorrect_answers) > 2 else '',
                        'all_answers_shuffled': ' | '.join(shuffled_answers)
                    }
                    
                    writer.writerow(row)
            
            print(f"💾 CSV sauvé: {filename}")
            return filename
            
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde CSV: {e}")
            return None
    
    def create_progress_bar(self, current, total, width=40):
        """Crée une barre de progression"""
        if total == 0:
            return "[" + "=" * width + "] 100%"
        
        progress = min(current / total, 1.0)
        filled = int(progress * width)
        bar = "=" * filled + "-" * (width - filled)
        percentage = progress * 100
        
        return f"[{bar}] {percentage:5.1f}%"
    
    def create_final_csv(self, questions):
        """Crée UN SEUL fichier CSV final"""
        if not questions:
            print("❌ Aucune question à sauvegarder")
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trivia_complete_{len(questions)}q_{timestamp}.csv"
        
        try:
            print(f"📊 Création du CSV final: {filename}")
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'id', 'category', 'type', 'difficulty', 'question', 'correct_answer',
                    'incorrect_answer_1', 'incorrect_answer_2', 'incorrect_answer_3', 'all_answers_shuffled'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for i, q in enumerate(questions, 1):
                    # Décoder le HTML
                    question = html.unescape(q['question'])
                    correct_answer = html.unescape(q['correct_answer'])
                    incorrect_answers = [html.unescape(ans) for ans in q['incorrect_answers']]
                    
                    # Créer toutes les réponses mélangées
                    all_answers = [correct_answer] + incorrect_answers
                    import random
                    shuffled_answers = all_answers.copy()
                    random.shuffle(shuffled_answers)
                    
                    # Préparer la ligne CSV
                    row = {
                        'id': i,
                        'category': q['category'],
                        'type': q['type'],
                        'difficulty': q['difficulty'],
                        'question': question,
                        'correct_answer': correct_answer,
                        'incorrect_answer_1': incorrect_answers[0] if len(incorrect_answers) > 0 else '',
                        'incorrect_answer_2': incorrect_answers[1] if len(incorrect_answers) > 1 else '',
                        'incorrect_answer_3': incorrect_answers[2] if len(incorrect_answers) > 2 else '',
                        'all_answers_shuffled': ' | '.join(shuffled_answers)
                    }
                    
                    writer.writerow(row)
                    
                    # Progress indicator pour l'écriture
                    if i % 1000 == 0:
                        print(f"✍️ Écriture: {i}/{len(questions)} lignes...")
            
            # Vérifier que le fichier existe et a du contenu
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                print(f"✅ CSV créé avec succès: {filename}")
                print(f"📁 Taille: {file_size/1024/1024:.2f} MB")
                print(f"📊 Contenu: {len(questions)} lignes + en-tête")
                
                # Créer un petit fichier de statistiques
                stats_file = filename.replace('.csv', '_stats.txt')
                with open(stats_file, 'w', encoding='utf-8') as f:
                    f.write(f"STATISTIQUES POUR {filename}\n")
                    f.write("="*50 + "\n")
                    f.write(f"Total questions: {len(questions)}\n")
                    f.write(f"Taille fichier: {file_size/1024/1024:.2f} MB\n")
                    f.write(f"Téléchargé le: {datetime.now()}\n")
                    f.write(f"Seuil MAX_DANGER: {self.MAX_DANGER}\n\n")
                    
                    # Compter par catégorie
                    categories = {}
                    for q in questions:
                        cat = q['category']
                        categories[cat] = categories.get(cat, 0) + 1
                    
                    f.write("RÉPARTITION PAR CATÉGORIE:\n")
                    for cat, count in sorted(categories.items()):
                        f.write(f"  {cat}: {count} questions\n")
                
                print(f"📊 Statistiques: {stats_file}")
                
                return filename
            else:
                print("❌ Erreur: fichier CSV non créé")
                return None
                
        except Exception as e:
            print(f"❌ Erreur création CSV: {e}")
            return None
    
    def estimate_time(self):
        """Estime le temps de téléchargement"""
        # Basé sur vos logs: ~5-6 questions/minute
        questions_per_minute = 6
        total_minutes = self.total_target / questions_per_minute
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        
        print(f"⏱️ Temps estimé pour {self.total_target} questions:")
        print(f"   À {questions_per_minute} questions/minute: {hours}h{minutes:02d}min")
        print(f"   Rythme observé dans vos logs précédents")
    
    def run(self):
        """Lance le téléchargement optimisé"""
        print("🎯 TÉLÉCHARGEUR OPTIMISÉ POUR 4620 QUESTIONS")
        print("="*60)
        
        self.estimate_time()
        
        print("\n💡 Stratégie adaptative:")
        print(f"  🚀 Mode RAPIDE (0-{self.MAX_DANGER}): 50 questions/lot, délai 5.2s")
        print(f"  🐌 Mode PRUDENT ({self.MAX_DANGER}+): 10 questions/lot, délai 8.0s")
        print("  📊 Un seul fichier CSV final")
        print("  💾 Sauvegardes plus fréquentes près de la fin")
        
        proceed = input(f"\n🤔 Télécharger les {self.total_target} questions? (o/N): ").strip().lower()
        if proceed not in ['o', 'oui', 'y', 'yes']:
            print("❌ Téléchargement annulé")
            return
        
        try:
            questions = self.download_all_4620()
            
            if questions:
                print(f"\n🎉 SUCCÈS! {len(questions)} questions téléchargées")
                
                # Créer le fichier CSV unique
                csv_file = self.create_final_csv(questions)
                
                if csv_file:
                    print(f"🎯 UN SEUL FICHIER CSV CRÉÉ: {csv_file}")
                    print(f"💡 Prêt pour Excel, Google Sheets, Python pandas, etc.")
                
            else:
                print("❌ Aucune question récupérée")
                
        except KeyboardInterrupt:
            print("\n⚠️ Téléchargement interrompu")
            # Sauvegarder ce qu'on a en CSV d'urgence
            if 'questions' in locals() and questions:
                print(f"\n💾 Sauvegarde d'urgence CSV de {len(questions)} questions...")
                self.create_final_csv(questions)

def main():
    downloader = OptimizedTriviaDownloader()
    downloader.run()

if __name__ == "__main__":
    main()