import requests
import os
import pandas as pd
import time
from datetime import datetime
import re
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import copy
import random

class MultiModelTriviaComparison:
    def __init__(self, ollama_url="http://localhost:11434"):
        self.base_url = ollama_url
        self.api_url = f"{ollama_url}/api/generate"
        self.models = []
        self.all_results = {}
        self.progress_lock = threading.Lock()
        self.print_lock = threading.Lock()
        self.prepared_questions = []  # Questions pré-préparées avec ordre fixe
        
    def thread_safe_print(self, message):
        """Impression thread-safe"""
        with self.print_lock:
            print(message)
    
    def prepare_questions(self, df, max_questions=None):
        """Prépare toutes les questions avec un ordre de réponses fixe"""
        if max_questions:
            df = df.head(max_questions)
        
        # Fixer le seed pour la reproductibilité
        random.seed(42)
        
        prepared = []
        
        for index, row in df.iterrows():
            question = row['question']
            correct_answer = row['correct_answer']
            
            # Récupérer les mauvaises réponses
            incorrect_answers = []
            for i in range(1, 4):
                col = f'incorrect_answer_{i}'
                if col in row and pd.notna(row[col]) and row[col].strip():
                    incorrect_answers.append(row[col])
            
            if len(incorrect_answers) < 2:
                continue
            
            # Créer et mélanger les réponses UNE SEULE FOIS
            all_answers = [correct_answer] + incorrect_answers
            shuffled_answers = all_answers.copy()
            random.shuffle(shuffled_answers)
            
            # Trouver la lettre correcte
            correct_letter = None
            options = []
            for i, answer in enumerate(shuffled_answers):
                letter = chr(65 + i)  # A, B, C, D
                options.append(f"{letter}) {answer}")
                if answer == correct_answer:
                    correct_letter = letter
            
            # Créer le prompt
            prompt = f"""You are a helpful assistant answering trivia questions. Answer with ONLY the letter (A, B, C, or D) that corresponds to the correct answer.

QUESTION: {question}

OPTIONS:
{chr(10).join(options)}

Think through this step by step if needed, but end your response with just the letter of the correct answer."""
            
            prepared_question = {
                'index': len(prepared) + 1,
                'question': question,
                'correct_answer': correct_answer,
                'correct_letter': correct_letter,
                'options': options,
                'prompt': prompt,
                'category': row.get('category', 'Unknown'),
                'difficulty': row.get('difficulty', 'Unknown'),
                'shuffled_answers': shuffled_answers
            }
            
            prepared.append(prepared_question)
        
        self.prepared_questions = prepared
        print(f"✅ {len(prepared)} questions préparées avec ordre fixe")
        
        return prepared
    
    def run_comparison(self, df, max_questions=None, delay=1.0, max_workers=None):
        """Lance la comparaison de tous les modèles avec questions cohérentes"""
        
        # Préparer les questions UNE SEULE FOIS
        prepared_questions = self.prepare_questions(df, max_questions)
        
        print(f"\n🏁 DÉBUT DE LA COMPARAISON")
        print(f"📊 Questions à tester: {len(prepared_questions)}")
        print(f"🤖 Modèles à tester: {len(self.models)}")
        
        # Calculer le nombre optimal de workers
        if max_workers is None:
            max_workers = min(len(self.models), 4)
        
        print(f"🔄 Threads parallèles: {max_workers}")
        print("="*60)
        
        model_summaries = []
        all_detailed_results = []
        
        # Progress tracking
        total_models = len(self.models)
        completed_models = 0
        progress_queue = Queue()
        
        def progress_updater():
            """Thread pour mettre à jour le progrès global"""
            nonlocal completed_models
            while completed_models < total_models:
                try:
                    update = progress_queue.get(timeout=1)
                    if update == "COMPLETE":
                        completed_models += 1
                        with self.print_lock:
                            print(f"\n🏁 Progrès global: {completed_models}/{total_models} modèles terminés")
                except:
                    continue
        
        # Démarrer le thread de suivi de progrès
        progress_thread = threading.Thread(target=progress_updater, daemon=True)
        progress_thread.start()
        
        # Exécuter les tests en parallèle
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Soumettre tous les jobs
            future_to_model = {}
            for model in self.models:
                future = executor.submit(
                    self.test_single_model_threaded, 
                    model, prepared_questions, delay, progress_queue
                )
                future_to_model[future] = model['name']
            
            # Collecter les résultats au fur et à mesure
            for future in as_completed(future_to_model):
                model_name = future_to_model[future]
                try:
                    results, accuracy, model_info = future.result()
                    
                    model_summaries.append({
                        'model': model_name,
                        'accuracy': accuracy,
                        'correct': sum(1 for r in results if r['is_correct']),
                        'total': len(results),
                        'size_gb': model_info['size'] / (1024**3) if model_info['size'] else 0
                    })
                    
                    all_detailed_results.extend(results)
                    self.all_results[model_name] = results
                    
                except Exception as e:
                    self.thread_safe_print(f"❌ Erreur avec {model_name}: {e}")
                    model_summaries.append({
                        'model': model_name,
                        'accuracy': 0,
                        'correct': 0,
                        'total': 0,
                        'size_gb': 0
                    })
        
        # Afficher le classement final
        self.show_final_comparison(model_summaries, all_detailed_results)
        
        return model_summaries, all_detailed_results
    
    def test_single_model_threaded(self, model_info, prepared_questions, delay=1.0, progress_queue=None):
        """Version thread-safe du test d'un modèle avec questions pré-préparées"""
        model_name = model_info['name']
        thread_id = threading.current_thread().name
        
        self.thread_safe_print(f"\n🚀 [{thread_id}] Démarrage test de {model_name}")
        
        results = []
        correct_count = 0
        total_count = 0
        extraction_failures = 0
        start_time = time.time()
        
        for q_data in prepared_questions:
            total_count += 1
            
            # Progress update
            if total_count % 5 == 0 or total_count == 1:
                accuracy = (correct_count / total_count) * 100
                self.thread_safe_print(f"📊 [{thread_id}] {model_name}: Q{total_count} - {accuracy:.1f}%")
            
            # Poser la question avec le prompt pré-préparé
            success, ai_response = self.ask_model(model_name, q_data['prompt'])
            
            if success:
                ai_letter = self.extract_letter_choice(ai_response)
                
                if ai_letter is None:
                    extraction_failures += 1
                    is_correct = False
                    ai_letter = 'NONE'
                else:
                    is_correct = (ai_letter == q_data['correct_letter'])
                    if is_correct:
                        correct_count += 1
                
                result = {
                    'model': model_name,
                    'question_num': total_count,
                    'category': q_data['category'],
                    'difficulty': q_data['difficulty'],
                    'question': q_data['question'],
                    'correct_answer': q_data['correct_answer'],
                    'correct_letter': q_data['correct_letter'],
                    'ai_response': ai_response,
                    'ai_letter': ai_letter,
                    'is_correct': is_correct,
                    'options': '; '.join(q_data['options']),
                    'response_time': None
                }
            else:
                result = {
                    'model': model_name,
                    'question_num': total_count,
                    'category': q_data['category'],
                    'difficulty': q_data['difficulty'],
                    'question': q_data['question'],
                    'correct_answer': q_data['correct_answer'],
                    'correct_letter': q_data['correct_letter'],
                    'ai_response': ai_response,
                    'ai_letter': 'ERROR',
                    'is_correct': False,
                    'options': '; '.join(q_data['options']),
                    'response_time': None
                }
            
            results.append(result)
            
            if delay > 0:
                time.sleep(delay)
        
        elapsed = time.time() - start_time
        final_accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0
        final_extraction_rate = ((total_count - extraction_failures) / total_count) * 100 if total_count > 0 else 0
        
        self.thread_safe_print(f"\n✅ [{thread_id}] TERMINÉ - {model_name}:")
        self.thread_safe_print(f"   📊 Précision: {final_accuracy:.1f}% ({correct_count}/{total_count})")
        self.thread_safe_print(f"   🔍 Extraction: {final_extraction_rate:.0f}%")
        self.thread_safe_print(f"   ⏱️ Temps: {elapsed/60:.1f} min")
        
        # Signaler la completion
        if progress_queue:
            progress_queue.put("COMPLETE")
        
        return results, final_accuracy, model_info
    
    def test_single_model_verbose(self, model_info, prepared_questions, delay=1.0):
        """Version verbose pour debug - affiche chaque question"""
        model_name = model_info['name']
        
        print(f"\n🤖 TEST DE {model_name}")
        print("-" * 50)
        
        results = []
        correct_count = 0
        total_count = 0
        extraction_failures = 0
        start_time = time.time()
        
        for q_data in prepared_questions:
            total_count += 1
            
            print(f"\n📝 Question {total_count}:")
            print(f"❓ {q_data['question']}")
            print(f"✅ Bonne réponse: {q_data['correct_letter']} ({q_data['correct_answer']})")
            print("📋 Options:")
            for option in q_data['options']:
                print(f"   {option}")
            
            # Poser la question
            success, ai_response = self.ask_model(model_name, q_data['prompt'])
            
            if success:
                # Afficher la réponse brute du modèle (tronquée si trop longue)
                display_response = ai_response
                if len(display_response) > 200:
                    display_response = display_response[:200] + "..."
                
                print(f"🤖 Réponse brute du modèle:")
                print(f"   '{display_response}'")
                
                ai_letter = self.extract_letter_choice(ai_response)
                
                if ai_letter is None:
                    extraction_failures += 1
                    is_correct = False
                    ai_letter = 'NONE'
                    print(f"❌ Extraction échouée - aucune lettre trouvée")
                else:
                    is_correct = (ai_letter == q_data['correct_letter'])
                    print(f"🔍 Lettre extraite: {ai_letter}")
                    
                    if is_correct:
                        print(f"✅ CORRECT! ({ai_letter} = {q_data['correct_letter']})")
                        correct_count += 1
                    else:
                        print(f"❌ INCORRECT ({ai_letter} ≠ {q_data['correct_letter']})")
                
                result = {
                    'model': model_name,
                    'question_num': total_count,
                    'category': q_data['category'],
                    'difficulty': q_data['difficulty'],
                    'question': q_data['question'],
                    'correct_answer': q_data['correct_answer'],
                    'correct_letter': q_data['correct_letter'],
                    'ai_response': ai_response,
                    'ai_letter': ai_letter,
                    'is_correct': is_correct,
                    'options': '; '.join(q_data['options']),
                    'response_time': None
                }
            else:
                print(f"❌ ERREUR du modèle: {ai_response}")
                result = {
                    'model': model_name,
                    'question_num': total_count,
                    'category': q_data['category'],
                    'difficulty': q_data['difficulty'],
                    'question': q_data['question'],
                    'correct_answer': q_data['correct_answer'],
                    'correct_letter': q_data['correct_letter'],
                    'ai_response': ai_response,
                    'ai_letter': 'ERROR',
                    'is_correct': False,
                    'options': '; '.join(q_data['options']),
                    'response_time': None
                }
            
            results.append(result)
            
            # Affichage du score en cours
            accuracy = (correct_count / total_count) * 100
            extraction_rate = ((total_count - extraction_failures) / total_count) * 100 if total_count > 0 else 0
            
            print(f"📊 Score actuel: {accuracy:.1f}% ({correct_count}/{total_count}) | Extraction: {extraction_rate:.0f}%")
            
            if delay > 0:
                time.sleep(delay)
        
        elapsed = time.time() - start_time
        final_accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0
        final_extraction_rate = ((total_count - extraction_failures) / total_count) * 100 if total_count > 0 else 0
        
        print(f"\n🏁 RÉSULTAT FINAL - {model_name}:")
        print(f"   📊 Précision: {final_accuracy:.1f}% ({correct_count}/{total_count})")
        print(f"   🔍 Extraction: {final_extraction_rate:.0f}%")
        print(f"   ⏱️ Temps: {elapsed/60:.1f} minutes")
        
        if extraction_failures > 0:
            print(f"   ⚠️ {extraction_failures} échecs d'extraction de lettres")
        
        return results, final_accuracy

    def get_available_models(self):
        """Récupère tous les modèles disponibles sur Ollama"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json().get('models', [])
                
                # Filtrer les modèles de texte (exclure embed)
                text_models = []
                for model in models_data:
                    name = model['name']
                    if 'embed' not in name.lower() and 'vision' not in name.lower():
                        text_models.append({
                            'name': name,
                            'id': model['model'],
                            'size': model.get('size', 0)
                        })
                
                self.models = text_models
                print("✅ Ollama accessible!")
                print(f"🤖 Modèles texte disponibles: {len(text_models)}")
                for model in text_models:
                    size_gb = model['size'] / (1024**3) if model['size'] else 0
                    print(f"  • {model['name']} ({size_gb:.1f} GB)")
                
                return True
            return False
        except:
            print("❌ Ollama non accessible")
            return False
    
    def extract_letter_choice(self, ai_response):
        """Extrait la lettre de choix avec amélioration spécifique pour Qwen et autres modèles"""
        
        # Nettoyer la réponse
        response = ai_response.strip()
        
        # 1. Pour les modèles avec balises <think> (Qwen, DeepSeek-R1)
        if '</think>' in response:
            # Prendre tout ce qui vient après la dernière balise </think>
            parts = response.split('</think>')
            if len(parts) > 1:
                post_think = parts[-1].strip()
                
                # Chercher une lettre seule sur une ligne
                lines = post_think.split('\n')
                for line in lines:
                    line = line.strip()
                    if re.match(r'^[ABCD]$', line.upper()):
                        return line.upper()
                
                # Chercher dans le texte après </think>
                letters = re.findall(r'\b[ABCD]\b', post_think.upper())
                if letters:
                    return letters[-1]
        
        # 2. Chercher une lettre seule à la fin de la réponse
        lines = response.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line and re.match(r'^[ABCD]$', line.upper()):
                return line.upper()
        
        # 3. Patterns spécifiques pour "the answer is X"
        answer_patterns = [
            r'(?:the\s+)?(?:correct\s+)?answer\s+is\s+([ABCD])\b',
            r'(?:choose|select)\s+([ABCD])\b',
            r'option\s+([ABCD])\b',
            r'([ABCD])\s*is\s+(?:the\s+)?(?:correct\s+)?(?:answer|choice)',
            r'(?:my\s+)?(?:final\s+)?(?:answer|choice)(?:\s+is)?\s*:?\s*([ABCD])\b'
        ]
        
        for pattern in answer_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                return matches[-1].upper()
        
        # 4. Chercher toutes les lettres et prendre la dernière
        letters = re.findall(r'\b[ABCD]\b', response.upper())
        if letters:
            return letters[-1]
        
        # 5. Chercher des patterns plus larges
        broader_patterns = [
            r'([ABCD])\)',  # A), B), etc.
            r'\(([ABCD])\)',  # (A), (B), etc.
            r'letter\s+([ABCD])',
            r'option\s+([ABCD])',
        ]
        
        for pattern in broader_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                return matches[-1].upper()
        
        return None

    def ask_model(self, model_name, prompt, timeout=30):
        """Pose une question à un modèle spécifique avec paramètres optimisés"""
        
        # Configuration spécifique par modèle - CORRIGÉE
        if "deepseek" in model_name.lower():
            timeout = 120
            max_tokens = 2000
            temperature = 0.0
        elif "qwen" in model_name.lower():
            timeout = 60
            # CORRECTION: Plus de tokens pour Qwen, même pour 0.6b
            max_tokens = 500 if "0.6b" in model_name else 1000
            temperature = 0.1
        elif "codellama" in model_name.lower():
            timeout = 45
            max_tokens = 300
            temperature = 0.1
        elif "llama" in model_name.lower():
            timeout = 45
            max_tokens = 300
            temperature = 0.1
        elif "gemma" in model_name.lower():
            timeout = 45
            max_tokens = 300
            temperature = 0.1
        elif "mistral" in model_name.lower():
            timeout = 45
            max_tokens = 300
            temperature = 0.1
        else:
            max_tokens = 300
            temperature = 0.1
        
        # Prompt amélioré pour forcer une réponse claire
        enhanced_prompt = f"""{prompt}

    IMPORTANT: After your reasoning, provide your final answer as just the letter (A, B, C, or D) on a new line."""
        
        data = {
            "model": model_name,
            "prompt": enhanced_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "max_tokens": max_tokens,
                "stop": ["\n\nQUESTION:", "\n\n---"]  # Arrêter à la prochaine question
            }
        }
        
        try:
            response = requests.post(self.api_url, json=data, timeout=timeout)
            
            if response.status_code == 200:
                response_data = response.json()
                ai_response = response_data.get('response', '').strip()
                return True, ai_response
            else:
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, f"TIMEOUT ({timeout}s)"
        except Exception as e:
            return False, f"ERROR: {str(e)[:50]}"

    # Fonction de test pour vérifier l'extraction
    def test_extraction():
        """Test la fonction d'extraction avec des exemples réels"""
        
        # Exemple de réponse Qwen
        qwen_response = """<think>
    Okay, so the question is asking who the singer is for Fall Out Boy. The options are A) Brendon Urie, B) Gary Lee Weinrib, C) Pete Wentz, D) Patrick Stump.

    First, I need to recall who Fall Out Boy is and who their singer is. Fall Out Boy is an American rock band formed in 2001. The band consists of Patrick Stump (lead vocals), Pete Wentz (bass), Joe Trohman (guitar), and Andy Hurley (drums).

    So the singer for Fall Out Boy is Patrick Stump, which corresponds to option D.
    </think>

    The answer is D."""
        
        # Tester l'extraction
        comparator = MultiModelTriviaComparison()
        result = comparator.extract_letter_choice(qwen_response)
        print(f"Extraction result: {result}")  # Devrait retourner 'D' 

    def load_trivia_csv(self, csv_path):
        """Charge le fichier CSV"""
        try:
            df = pd.read_csv(csv_path)
            print(f"✅ CSV chargé: {len(df)} questions")
            
            required_cols = ['question', 'correct_answer', 'incorrect_answer_1']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                print(f"❌ Colonnes manquantes: {missing_cols}")
                return None
            
            return df
        except Exception as e:
            print(f"❌ Erreur lecture CSV: {e}")
            return None
    
    def show_final_comparison(self, model_summaries, all_results):
        """Affiche la comparaison finale avec vérification de cohérence"""
        print("\n" + "="*70)
        print("🏆 CLASSEMENT FINAL DES MODÈLES")
        print("="*70)
        
        # Trier par précision
        sorted_models = sorted(model_summaries, key=lambda x: x['accuracy'], reverse=True)
        
        print(f"{'RANG':<4} {'MODÈLE':<20} {'PRÉCISION':<12} {'SCORE':<12} {'TAILLE':<8}")
        print("-" * 70)
        
        for i, model in enumerate(sorted_models, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i:2d}."
            
            print(f"{medal:<4} {model['model']:<20} {model['accuracy']:>6.1f}% "
                  f"{model['correct']:>3d}/{model['total']:<3d} {model['size_gb']:>6.1f}GB")
        
        # Vérification de cohérence
        print(f"\n🔍 VÉRIFICATION DE COHÉRENCE:")
        if len(all_results) > 0:
            df_all = pd.DataFrame(all_results)
            
            # Vérifier que tous les modèles ont les mêmes questions
            questions_per_model = df_all.groupby('model')['question_num'].count()
            if questions_per_model.nunique() == 1:
                print(f"   ✅ Tous les modèles testés sur {questions_per_model.iloc[0]} questions")
            else:
                print(f"   ⚠️ Nombre de questions différent par modèle: {dict(questions_per_model)}")
            
            # Vérifier la cohérence des bonnes réponses
            question_consistency = df_all.groupby('question_num')['correct_letter'].nunique()
            inconsistent_questions = question_consistency[question_consistency > 1]
            
            if len(inconsistent_questions) == 0:
                print(f"   ✅ Toutes les questions ont la même bonne réponse pour tous les modèles")
            else:
                print(f"   ❌ {len(inconsistent_questions)} questions avec bonnes réponses incohérentes!")
                for q_num in inconsistent_questions.index[:3]:  # Montrer les 3 premières
                    q_data = df_all[df_all['question_num'] == q_num][['model', 'correct_letter']].drop_duplicates()
                    print(f"      Q{q_num}: {dict(zip(q_data['model'], q_data['correct_letter']))}")
        
        # Analyse détaillée du top 3
        if len(sorted_models) >= 3:
            print(f"\n📊 ANALYSE DÉTAILLÉE TOP 3:")
            
            for rank, model in enumerate(sorted_models[:3], 1):
                model_name = model['model']
                model_results = [r for r in all_results if r['model'] == model_name]
                
                if model_results:
                    df_model = pd.DataFrame(model_results)
                    
                    print(f"\n{rank}. {model_name} ({model['accuracy']:.1f}%)")
                    
                    # Par difficulté
                    if 'difficulty' in df_model.columns:
                        diff_stats = df_model.groupby('difficulty')['is_correct'].agg(['count', 'sum', 'mean'])
                        print("   Par difficulté:")
                        for diff, stats in diff_stats.iterrows():
                            if stats['count'] > 0:
                                acc = stats['mean'] * 100
                                print(f"    • {diff}: {acc:5.1f}% ({int(stats['sum'])}/{int(stats['count'])})")
        
        # Recommandation
        if sorted_models:
            best = sorted_models[0]
            print(f"\n🎯 RECOMMANDATION:")
            print(f"   Meilleur modèle: {best['model']} avec {best['accuracy']:.1f}% de précision")
            
            if len(sorted_models) > 1:
                second = sorted_models[1]
                diff = best['accuracy'] - second['accuracy']
                if diff < 2:
                    print(f"   ⚖️ Très proche de {second['model']} (différence: {diff:.1f}%)")
                elif best['size_gb'] > second['size_gb'] * 1.5:
                    print(f"   💡 {second['model']} pourrait être un bon compromis (plus petit)")
    
    def save_comparison_results(self, model_summaries, all_results):
        """Sauvegarde tous les résultats"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Résumé des modèles
        summary_file = f"model_comparison_summary_{timestamp}.csv"
        summary_df = pd.DataFrame(model_summaries)
        summary_df = summary_df.sort_values('accuracy', ascending=False)
        summary_df.to_csv(summary_file, index=False)
        
        # Résultats détaillés
        detailed_file = f"model_comparison_detailed_{timestamp}.csv"
        detailed_df = pd.DataFrame(all_results)
        detailed_df.to_csv(detailed_file, index=False)
        
        print(f"\n💾 FICHIERS SAUVEGARDÉS:")
        print(f"   📊 Résumé: {summary_file}")
        print(f"   📋 Détails: {detailed_file}")
        
        return summary_file, detailed_file
    
    def run_interactive(self):
        """Interface interactive pour la comparaison"""
        print("🏁 COMPARATEUR DE MODÈLES TRIVIA - VERSION CORRIGÉE")
        print("="*55)
        
        # Récupérer les modèles
        if not self.get_available_models():
            return
        
        if len(self.models) == 0:
            print("❌ Aucun modèle texte trouvé")
            return
        
        # Sélection des modèles
        print(f"\n🤖 SÉLECTION DES MODÈLES:")
        print("0. Tous les modèles")
        for i, model in enumerate(self.models, 1):
            size_gb = model['size'] / (1024**3) if model['size'] else 0
            print(f"{i}. {model['name']} ({size_gb:.1f}GB)")
        
        selection = input(f"\nQuels modèles tester? (0 pour tous, ou 1,2,3): ").strip()
        
        if selection == "0" or not selection:
            selected_models = self.models
        else:
            try:
                indices = [int(x.strip())-1 for x in selection.split(',')]
                selected_models = [self.models[i] for i in indices if 0 <= i < len(self.models)]
            except:
                print("❌ Sélection invalide, tous les modèles seront testés")
                selected_models = self.models
        
        self.models = selected_models
        print(f"✅ {len(self.models)} modèle(s) sélectionné(s)")
        
        # Fichier CSV
        csv_files = [f for f in os.listdir('.') if f.endswith('.csv') and 'trivia' in f]
        
        if csv_files:
            csv_path = csv_files[0]
            print(f"\n📁 Fichier trouvé: {csv_path}")
            use_file = input("Utiliser ce fichier? (o/N): ").strip().lower()
            if use_file not in ['o', 'oui', 'y', 'yes']:
                csv_path = input("📁 Chemin vers votre fichier CSV: ").strip()
        else:
            csv_path = input("📁 Chemin vers votre fichier CSV: ").strip()
        
        # Charger les données
        df = self.load_trivia_csv(csv_path)
        if df is None:
            return
        
        print(f"\n⚙️ CONFIGURATION")
        max_q = input(f"🎯 Nombre de questions par modèle (max {len(df)}, Entrée=toutes): ").strip()
        max_questions = int(max_q) if max_q.isdigit() else None
        
        delay_input = input("⏱️ Délai entre questions en secondes (défaut=1.0): ").strip()
        delay = float(delay_input) if delay_input else 1.0
        
        # Mode de test
        print(f"\n🔧 MODE DE TEST:")
        print("1. Mode parallèle (rapide)")
        print("2. Mode verbose (debug détaillé)")
        mode = input("Choisir le mode (1/2): ").strip()
        
        if mode == "2":
            # Mode verbose - un seul modèle à la fois avec détails
            print(f"\n📋 MODE VERBOSE SÉLECTIONNÉ")
            print("Ce mode teste un modèle à la fois avec affichage détaillé")
            
            # Préparer les questions
            prepared_questions = self.prepare_questions(df, max_questions)
            
            for model in self.models:
                proceed = input(f"\n🚀 Tester {model['name']}? (o/N): ").strip().lower()
                if proceed in ['o', 'oui', 'y', 'yes']:
                    results, accuracy = self.test_single_model_verbose(model, prepared_questions, delay)
                    
                    print(f"\n📊 RÉSULTAT {model['name']}: {accuracy:.1f}%")
                    
                    if len(self.models) > 1:
                        continue_test = input("Continuer avec le modèle suivant? (o/N): ").strip().lower()
                        if continue_test not in ['o', 'oui', 'y', 'yes']:
                            break
            
            print("\n✅ Test verbose terminé!")
            return
        
        # Mode parallèle (par défaut)
        # Configuration multi-threading
        print(f"\n🔄 CONFIGURATION MULTI-THREADING:")
        max_workers_input = input(f"Nombre de threads parallèles (défaut={min(len(self.models), 4)}, max={len(self.models)}): ").strip()
        max_workers = int(max_workers_input) if max_workers_input.isdigit() else min(len(self.models), 4)
        max_workers = min(max_workers, len(self.models))
        
        # Estimation
        actual_count = min(max_questions or len(df), len(df))
        total_questions = actual_count * len(self.models)
        
        # Temps estimé avec parallélisation
        if len(self.models) > 1:
            estimated_time_parallel = (total_questions * delay) / (60 * max_workers)
            estimated_time_sequential = (total_questions * delay) / 60
            time_saved = estimated_time_sequential - estimated_time_parallel
        else:
            estimated_time_parallel = (total_questions * delay) / 60
            time_saved = 0
        
        print(f"\n📋 RÉSUMÉ:")
        print(f"  • 🤖 Modèles: {len(self.models)}")
        print(f"  • 🎯 Questions par modèle: {actual_count}")
        print(f"  • 📊 Total questions: {total_questions}")
        print(f"  • 🔄 Threads parallèles: {max_workers}")
        print(f"  • 🕐 Temps estimé: {estimated_time_parallel:.1f} min")
        if time_saved > 0:
            print(f"  • ⚡ Temps économisé: {time_saved:.1f} min ({time_saved/estimated_time_sequential*100:.0f}%)")
        print(f"  • 🎲 Seed fixe: 42 (questions cohérentes)")
        
        proceed = input(f"\n🚀 Lancer la comparaison? (o/N): ").strip().lower()
        if proceed not in ['o', 'oui', 'y', 'yes']:
            print("❌ Comparaison annulée")
            return
        
        # Lancer la comparaison
        try:
            model_summaries, all_results = self.run_comparison(df, max_questions, delay, max_workers)
            
            # Sauvegarder
            self.save_comparison_results(model_summaries, all_results)
                
        except KeyboardInterrupt:
            print("\n⚠️ Comparaison interrompue!")

def main():
    comparator = MultiModelTriviaComparison()
    comparator.run_interactive()

if __name__ == "__main__":
    main()