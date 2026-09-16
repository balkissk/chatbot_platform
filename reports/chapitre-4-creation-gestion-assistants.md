# Chapitre 4 - Création et gestion des assistants conversationnels

## 1. Périmètre fonctionnel implémenté

| Domaine | Fonctionnalités réalisées | Rôles | Règles métier | Interface utilisateur | Serveur applicatif / données |
|---|---|---|---|---|---|
| Projets | Créer, consulter, rechercher, filtrer, trier, paginer, afficher en grille/tableau | Admin, Manager | Le nom est obligatoire. Description vide remplacée par `No description`. Création en statut `active`. | `ProjectsComponent`, `ProjectOverviewComponent`, `ProjectSettingsComponent` | `POST /projects`, `GET /projects/query`, `GET /projects/{id}`, modèle `Project(id, name, description, user_id, status, created_at, archived_at, deleted_at)` |
| Projets | Modifier nom/description | Admin, Manager | Le nom ne peut pas être vide. Audit `PROJECT_RENAMED` ou `PROJECT_UPDATED`. | Liste projets, aperçu projet, paramètres projet | `PUT /projects/{id}` |
| Projets | Dupliquer, archiver, restaurer, supprimer | Admin, Manager | Archive : `status=archived`, `archived_at`. Suppression logique : `status=disabled`, `deleted_at`, pas de suppression physique du projet. Projet archivé non modifiable côté interface. | Menu actions projet | `POST /projects/{id}/duplicate`, `PUT /archive`, `PUT /restore`, `DELETE /projects/{id}` |
| Assistants | Lister les assistants d’un projet, rechercher, filtrer par statut, paginer | Admin, Manager | Manager ne voit que les assistants de ses projets. Admin voit l’ensemble. | `ChatbotsComponent` | `GET /projects/{project_id}/chatbots`, `Chatbot.project_id` |
| Assistants | Créer un assistant | Admin, Manager | Nom obligatoire. Modes autorisés : `scratch`, `template`, `ai`, `blank`; `blank` devient `scratch`. Création d’une première version `draft`, d’une configuration LLM par défaut et d’un flow de départ `blank`. | `AssistantCreationWizardComponent` intégré dans `ChatbotsComponent` | `POST /chatbots`, `Chatbot`, `VersionChatbot`, `LLMConfig`, `Flow` |
| Assistant de création guidée | Étape 1 : choisir l’objectif métier. Étape 2 : choisir le mode de départ. Étape 3 : saisir nom, description, langue, canal | Admin, Manager via création | Objectifs : support client, connaissance interne, formation/certification, génération de leads, personnalisé. Langues : `en`, `fr`. Canaux : `public_chat`, `web_widget`, `rest_public_api`. | `assistant-creation-wizard.component.*` | Schéma `ChatbotCreate`, validateurs langue/canal |
| Modèles prédéfinis | Charger les modèles compatibles avec l’objectif, sélectionner un modèle, confirmer le remplacement du brouillon | Admin, Manager | Application du modèle sur le flow brouillon courant. Les versions publiées ne sont pas modifiées. Modèles intégrés en lecture seule. Modèles personnalisés possibles côté serveur. | `TemplateSelectionComponent` | `GET /flow-templates?purpose=&exposed_only=true`, `POST /flows/{flow_id}/template`, `services/templates.py` |
| Aperçu assistant | Voir identité, statut, objectif, langue, canal, résumé des versions, raccourcis vers espaces de travail | Admin, Manager | Vue de consultation. Certains raccourcis mènent vers chapitres hors périmètre. | `AssistantOverviewComponent`, panneau info dans `ChatbotsComponent` | `GET /chatbots/{id}` |
| Paramètres assistant | Modifier nom, description, langue, canal | Admin, Manager | Nom obligatoire. Le mode de création ne peut pas être changé après création. | `AssistantSettingsComponent`, panneau paramètres dans `ChatbotsComponent` | `PUT /chatbots/{id}`, `ChatbotUpdate` |
| Statut / cycle de vie | Activer/désactiver assistant ; archiver/restaurer projet ; supprimer assistant | Admin, Manager | `is_active` contrôle l’activation. Suppression assistant = suppression physique avec conversations, versions, flows, config LLM et données associées. Projet archivé bloque les actions de modification côté interface. | `ChatbotsComponent`, `AssistantSettingsComponent`, `ProjectsComponent` | `PUT /chatbots/{id}/status`, `DELETE /chatbots/{id}` |

Différence de permissions : l’Admin peut accéder aux projets/assistants globalement ; le Manager est limité à ses propres projets via `Project.user_id`. Les routes `/chatbots/{id}/setup`, `/setup/template-draft` et `/setup/ai-draft` sont réservées au rôle `manager`.

## 2. Sprint Backlog

| ID | User Story | Tâches principales | Priorité |
|---|---|---|---|
| US-01 | En tant qu’Admin ou Manager, je veux créer un projet afin d’organiser mes assistants. | Formulaire de création, validation du nom, persistance, affichage dans la liste | Haute |
| US-02 | En tant qu’utilisateur autorisé, je veux consulter, rechercher et filtrer mes projets. | Liste paginée, recherche, filtres statut/activité/nombre d’assistants, tri, vue grille/table | Haute |
| US-03 | En tant qu’utilisateur autorisé, je veux gérer le cycle de vie d’un projet. | Renommer, dupliquer, archiver, restaurer, supprimer logiquement | Haute |
| US-04 | En tant qu’utilisateur autorisé, je veux créer un assistant dans un projet. | Wizard en 3 étapes, choix objectif/mode/langue/canal, création brouillon | Haute |
| US-05 | En tant qu’utilisateur autorisé, je veux démarrer un assistant depuis un modèle prédéfini. | Catalogue filtré par objectif, sélection, confirmation, application au brouillon | Haute |
| US-06 | En tant qu’utilisateur autorisé, je veux consulter la fiche d’un assistant. | Aperçu, métadonnées, statut, résumé des versions, raccourcis | Moyenne |
| US-07 | En tant qu’utilisateur autorisé, je veux modifier la configuration générale d’un assistant. | Formulaire paramètres, validation, sauvegarde nom/description/langue/canal | Haute |
| US-08 | En tant qu’utilisateur autorisé, je veux activer, désactiver ou supprimer un assistant. | Changement `is_active`, confirmation suppression, nettoyage des données associées | Haute |
| US-09 | En tant que Manager, je veux mettre à jour le setup guidé d’un assistant depuis l’espace de construction. | Chargement setup, sauvegarde champs, conservation du mode de création | Moyenne |

## 3. Acteurs et permissions

| Acteur | Permissions implémentées dans le périmètre |
|---|---|
| Administrateur | Accède au dashboard, liste tous les projets et assistants, crée/modifie/duplique/archive/restaure/supprime les projets, crée/modifie/active/désactive/supprime les assistants, consulte/applique les modèles. |
| Manager | Accède au dashboard, gère uniquement ses projets (`Project.user_id == current_user.id`), crée/modifie/duplique/archive/restaure/supprime ses projets, gère les assistants de ses projets, accède au setup guidé avancé. |
| Utilisateur final public | À ne pas inclure dans ce chapitre : les canaux publics et l’accès public relèvent du Chapitre 6. |

## 4. Contenu du diagramme de cas d’utilisation

Acteurs :
- Administrateur
- Manager

Cas d’utilisation :
- Gérer les projets
- Créer un projet
- Consulter la liste des projets
- Rechercher et filtrer les projets
- Modifier un projet
- Dupliquer un projet
- Archiver / restaurer un projet
- Supprimer un projet
- Gérer les assistants d’un projet
- Créer un assistant conversationnel
- Choisir l’objectif de l’assistant
- Choisir le mode de création
- Configurer l’identité de base
- Utiliser un modèle prédéfini
- Consulter un assistant
- Modifier la configuration d’un assistant
- Activer / désactiver un assistant
- Supprimer un assistant

Associations :
- Administrateur : tous les cas d’utilisation ci-dessus.
- Manager : mêmes cas, mais uniquement sur ses projets et assistants.
- Manager : setup guidé avancé depuis l’espace de construction.

Relations `<<include>>` :
- Créer un assistant conversationnel `<<include>>` Choisir l’objectif de l’assistant.
- Créer un assistant conversationnel `<<include>>` Choisir le mode de création.
- Créer un assistant conversationnel `<<include>>` Configurer l’identité de base.
- Utiliser un modèle prédéfini `<<include>>` Sélectionner un modèle compatible.
- Utiliser un modèle prédéfini `<<include>>` Remplacer le flow brouillon.
- Gérer les assistants d’un projet `<<include>>` Consulter un assistant.
- Modifier la configuration d’un assistant `<<include>>` Valider les champs obligatoires.

Relations `<<extend>>` :
- Utiliser un modèle prédéfini `<<extend>>` Créer un assistant conversationnel, lorsque le mode choisi est `template`.
- Archiver / restaurer un projet `<<extend>>` Gérer les projets.
- Supprimer un assistant `<<extend>>` Gérer les assistants d’un projet.

## 5. Cas d’utilisation textuels

### UC-01 - Créer un projet

Acteurs : Administrateur, Manager.

Préconditions : utilisateur authentifié avec rôle `admin` ou `manager`.

Postconditions : un projet `active` est créé et rattaché à l’utilisateur courant.

Scénario nominal :
1. L’acteur ouvre la page Projets.
2. Il clique sur `New Project`.
3. Il saisit le nom et éventuellement une description.
4. Le système valide que le nom n’est pas vide.
5. Le serveur crée le projet avec `user_id=current_user.id`.
6. Le projet apparaît dans la liste.

Alternatives :
- Description vide : le système enregistre `No description`.

Exceptions :
- Nom vide : création refusée.
- Erreur serveur : message d’échec affiché.

### UC-02 - Créer un assistant conversationnel

Acteurs : Administrateur, Manager.

Préconditions : projet existant, accessible et non archivé côté interface.

Postconditions : un assistant est créé avec une première version `draft`.

Scénario nominal :
1. L’acteur ouvre les assistants d’un projet.
2. Il lance l’assistant de création guidée.
3. Il choisit l’objectif métier.
4. Il choisit le mode de création.
5. Il renseigne nom, description, langue et canal.
6. Le serveur crée `Chatbot`, `VersionChatbot(status=draft)`, `LLMConfig` et un flow initial.
7. L’interface redirige vers Flow Builder, sélection de modèle ou générateur IA selon le mode.

Alternatives :
- Mode `template` : redirection vers l’écran de modèles.
- Mode `ai` : redirection vers l’écran de génération IA.
- Mode `scratch` : redirection vers le Flow Builder.

Exceptions :
- Nom vide : création refusée.
- Mode de création non supporté : erreur `400`.
- Projet inaccessible : erreur `404`.

### UC-03 - Appliquer un modèle prédéfini

Acteurs : Administrateur, Manager.

Préconditions : assistant existant, flow brouillon disponible.

Postconditions : le flow brouillon est remplacé par le modèle sélectionné.

Scénario nominal :
1. L’acteur ouvre l’écran de sélection des modèles.
2. Le système charge les modèles exposés compatibles avec l’objectif de l’assistant.
3. L’acteur sélectionne un modèle.
4. Il confirme le remplacement du brouillon.
5. Le serveur valide la structure du modèle.
6. Le serveur remplace les nœuds et transitions du flow courant.
7. L’interface redirige vers le Flow Builder.

Alternatives :
- Aucun modèle compatible : un état vide est affiché.

Exceptions :
- Aucun flow brouillon disponible : message d’erreur.
- Modèle invalide ou inconnu : application refusée.

### UC-04 - Modifier la configuration d’un assistant

Acteurs : Administrateur, Manager.

Préconditions : assistant accessible.

Postconditions : les métadonnées de l’assistant sont mises à jour.

Scénario nominal :
1. L’acteur ouvre les paramètres de l’assistant.
2. Il modifie nom, description, langue ou canal.
3. Le système valide le nom.
4. Le serveur sauvegarde les champs.
5. L’interface affiche un message de succès.

Alternatives :
- Description vide : elle est enregistrée comme chaîne vide côté assistant.

Exceptions :
- Nom vide : sauvegarde refusée.
- Tentative de changer le mode de création via `PUT /chatbots/{id}` : refusée.

### UC-05 - Gérer le cycle de vie d’un assistant

Acteurs : Administrateur, Manager.

Préconditions : assistant accessible et projet non archivé côté interface.

Postconditions : assistant activé/désactivé ou supprimé.

Scénario nominal :
1. L’acteur ouvre les paramètres ou la liste des assistants.
2. Il active ou désactive l’assistant.
3. Le serveur met à jour `Chatbot.is_active`.
4. L’interface actualise le statut.

Alternative :
- Suppression : l’acteur confirme, puis le serveur supprime l’assistant et ses données associées.

Exceptions :
- Projet archivé : les actions de modification sont désactivées dans l’interface.
- Assistant inaccessible : erreur `404`.

## 6. Conception

La relation implémentée est : un `Project` possède plusieurs `Chatbot`, et chaque `Chatbot` appartient à un seul `Project` via `chatbots.project_id`.

Cardinalité :
- `Project 1 - 0..* Chatbot`
- `Chatbot 1 - 1..* VersionChatbot`
- `VersionChatbot 1 - 0..1 Flow`, avec contrainte unique sur `flows.version_id`

Propriété :
- Le projet est rattaché à `Project.user_id`.
- Le Manager ne peut accéder qu’aux projets dont il est propriétaire.
- L’Admin n’a pas cette restriction.

Identifiants importants :
- `Project.id`
- `Chatbot.id`
- `Chatbot.project_id`
- `Chatbot.active_version_id`
- `VersionChatbot.chatbot_id`
- `Flow.version_id`

Statuts :
- Projet : `active`, `draft`, `archived`, `disabled`.
- Assistant : `is_active`.
- Statut sérialisé assistant : `published` si au moins une version publiée existe, sinon `draft`.
- Version : `draft`, `published`, `archived`.

Suppression / archivage :
- Projet archivé : `status=archived`, `archived_at` renseigné ; les données restent.
- Projet supprimé : suppression logique avec `status=disabled`, `deleted_at`, et `archived_at` si absent.
- Assistant supprimé : suppression physique de l’assistant, conversations, versions, flows, configuration LLM et données liées.

Contraintes :
- `chatbots.project_id` référence `projects.id`.
- `versions.chatbot_id` référence `chatbots.id`.
- `flows.version_id` référence `versions.id` avec unicité.
- `llm_configs.version_id` est unique.
- Pas de contrainte unique visible sur les noms de projets ou d’assistants.

## 7. Diagrammes de séquence recommandés

### 7.1 Créer un projet

Participants : `ProjectsComponent`, `ApiService`, `project_routes.create_project`, `Project`, base de données.

Flux nominal : saisie formulaire, `POST /projects`, validation du nom, création `Project`, audit `PROJECT_CREATED`, réponse, actualisation de la liste.

Bloc alternatif : nom vide, erreur `400`.

### 7.2 Créer un assistant conversationnel

Participants : `ChatbotsComponent`, `AssistantCreationWizardComponent`, `ApiService`, `chatbot_routes.create_chatbot`, `Chatbot`, `VersionChatbot`, `LLMConfig`, `Flow`.

Flux nominal : choix objectif/mode/configuration, `POST /chatbots`, contrôle d’accès au projet, création assistant, création version `draft`, création configuration modèle par défaut, création flow `blank`, réponse, redirection selon mode.

Blocs alternatifs :
- `template` : redirection vers `TemplateSelectionComponent`.
- `ai` : redirection vers générateur IA.
- `scratch` : redirection vers Flow Builder.

### 7.3 Appliquer un modèle prédéfini

Participants : `TemplateSelectionComponent`, `ApiService`, `flow_routes.list_flow_templates`, `flow_routes.apply_flow_template`, `services.templates`, `FlowNode`, `FlowTransition`.

Flux nominal : charger assistant, charger modèles filtrés, sélectionner, confirmer, récupérer le flow brouillon, `POST /flows/{flow_id}/template`, validation de la structure, suppression des anciens nœuds/transitions, insertion des nouveaux nœuds/transitions, redirection Flow Builder.

Blocs alternatifs : aucun modèle compatible ; flow absent ; modèle invalide.

### 7.4 Modifier les paramètres d’un assistant

Participants : `AssistantSettingsComponent`, `ApiService`, `chatbot_routes.update_chatbot`, `Chatbot`.

Flux nominal : charger assistant, modifier formulaire, `PUT /chatbots/{id}`, validation nom/langue/canal, mise à jour, audit `CHATBOT_UPDATED`, message de succès.

Bloc alternatif : activation/désactivation via `PUT /chatbots/{id}/status`.

## 8. Réalisation

### 4.5.1 Gestion des projets

Présenter la liste des projets, la recherche, les filtres, le tri, les vues grille/tableau, la création, la modification, la duplication, l’archivage, la restauration et la suppression logique.

### 4.5.2 Création d’un assistant conversationnel

Expliquer la création serveur : assistant, version brouillon, configuration par défaut et flow initial.

### 4.5.3 Assistant de création guidée

Décrire le wizard en 3 étapes : objectif, mode de création et configuration de base.

### 4.5.4 Utilisation des modèles prédéfinis

Garder cette section, mais préciser que le modèle est appliqué après création et remplace le flow brouillon. Ne pas présenter cela comme une publication.

### 4.5.5 Configuration des assistants

Traiter le nom, la description, la langue, le canal, l’objectif, le mode de création conservé et les champs IA de provenance côté setup.

### 4.5.6 Consultation et modification des assistants

Présenter la liste des assistants, l’aperçu, le panneau info, la page overview et la page settings.

### 4.5.7 Gestion du cycle de vie et des statuts

Présenter l’activation/désactivation, l’archivage/restauration projet, la suppression logique projet et la suppression physique assistant. Éviter la publication et le versioning ici.

Renommage conseillé : `4.5.7 Gestion des statuts internes et de l’archivage`.

## 9. Interfaces à inclure

| Interface | Ce qu’elle démontre | Légende proposée |
|---|---|---|
| Page Projets | Vue globale des projets, indicateurs, recherche, filtres, actions | Figure 4.x - Interface de gestion des projets |
| Modale création projet | Création d’un espace de travail | Figure 4.x - Formulaire de création d’un projet |
| Liste des assistants d’un projet | Assistants rattachés au projet, filtres, statut, actions | Figure 4.x - Liste des assistants conversationnels d’un projet |
| Assistant de création guidée | Étapes objectif, mode, configuration | Figure 4.x - Assistant de création guidée d’un assistant conversationnel |
| Sélection des modèles | Catalogue de modèles compatibles et confirmation de remplacement du brouillon | Figure 4.x - Sélection d’un modèle prédéfini |
| Aperçu assistant | Métadonnées et raccourcis de gestion | Figure 4.x - Vue d’ensemble d’un assistant conversationnel |
| Paramètres assistant | Modification nom, langue, canal, disponibilité, suppression | Figure 4.x - Configuration générale d’un assistant |

À éviter dans ce chapitre : captures centrées sur Flow Builder, Knowledge Base, Analytics, Versions, Deployment, public chat, widget ou API publique.

## 10. Tests et validation

| Objectif | Action / entrée | Résultat attendu |
|---|---|---|
| Créer un projet valide | Nom + description | Projet créé en statut `active`, visible dans la liste |
| Refuser projet sans nom | Soumettre nom vide | Bouton désactivé ou erreur `Project name is required` |
| Rechercher un projet | Saisir un terme existant | Liste filtrée sur nom/description |
| Filtrer projets archivés | Choisir statut `Archived` | Seuls les projets archivés apparaissent |
| Archiver un projet | Confirmer archive | Statut `archived`, actions de modification bloquées côté interface |
| Restaurer un projet | Cliquer `Restore Project` | Statut redevient `active` |
| Créer assistant depuis wizard | Choisir objectif, mode, nom, langue, canal | Assistant créé avec version `draft`, redirection selon mode |
| Refuser assistant sans nom | Terminer wizard sans nom | Finalisation impossible |
| Appliquer modèle | Choisir modèle compatible et confirmer | Flow brouillon remplacé, redirection vers Flow Builder |
| Modifier paramètres assistant | Changer nom/langue/canal | Données sauvegardées et affichées |
| Activer/désactiver assistant | Cliquer `Deactivate` ou `Activate` | `is_active` mis à jour |
| Supprimer assistant | Confirmer suppression | Assistant retiré de la liste |

Je n’ai pas constaté d’exécution de tests automatisés dans cette inspection ; ne pas affirmer qu’ils ont été lancés.

## 11. Incohérences / avertissements pour le rapport

- Ne pas inclure la publication, les versions publiées, le déploiement, les canaux publics, le widget et l’API publique dans le Chapitre 4.
- L’aperçu projet affiche des cartes `Publication Checklist`, `Release State`, Knowledge et Runtime : ces éléments existent dans l’interface mais doivent être traités dans les chapitres 5/6 selon votre découpage.
- Le wizard annonce `Use Template`, mais la création serveur crée d’abord un flow `blank`; le modèle est appliqué ensuite dans `TemplateSelectionComponent`.
- Le statut affiché `Live` côté liste peut dépendre de `is_active`, alors que le champ sérialisé `status` dépend de l’existence d’une version publiée. À formuler prudemment.
- Le projet est supprimé logiquement ; l’assistant est supprimé physiquement avec ses données associées.
- Les modèles prédéfinis contiennent des flows avec nœuds RAG/handoff, mais leur logique détaillée appartient aux chapitres Flow Builder et LLM/RAG.
- Le rôle `end_user` ne participe pas au périmètre Chapter 4.
- Le terme `Chatbot` est le nom technique du modèle ; dans le rapport, utiliser principalement `assistant conversationnel`.

## 12. Structure finale recommandée du Chapitre 4

Chapitre 4 - Création et gestion des assistants conversationnels

4.1 Introduction  
4.2 Backlog du sprint  
4.3 Analyse des besoins  
4.3.1 Besoins liés à la gestion des projets  
4.3.2 Besoins liés à la gestion des assistants conversationnels  
4.3.3 Acteurs et droits d’accès  
4.3.4 Diagramme de cas d’utilisation  
4.3.5 Description textuelle des cas d’utilisation  

4.4 Conception  
4.4.1 Relation entre projet et assistant conversationnel  
4.4.2 Conception de la création guidée des assistants  
4.4.3 Conception de la configuration et des statuts internes  
4.4.4 Diagrammes de séquence  

4.5 Réalisation  
4.5.1 Gestion des projets  
4.5.2 Création d’un assistant conversationnel  
4.5.3 Assistant de création guidée  
4.5.4 Utilisation des modèles prédéfinis  
4.5.5 Configuration générale des assistants  
4.5.6 Consultation et modification des assistants  
4.5.7 Gestion des statuts internes et de l’archivage  

4.6 Interfaces réalisées  
4.7 Tests et validation fonctionnelle  
4.8 Conclusion  

## Sources de code inspectées

- `frontend/src/app/app.routes.ts`
- `frontend/src/app/guards/role.guard.ts`
- `frontend/src/app/services/api.ts`
- `frontend/src/app/shared/assistant-options.ts`
- `frontend/src/app/pages/projects/projects.component.ts`
- `frontend/src/app/pages/projects/projects.component.html`
- `frontend/src/app/pages/projects/project-actions-menu.component.ts`
- `frontend/src/app/pages/projects/project-actions-menu.component.html`
- `frontend/src/app/pages/project-overview/project-overview.component.ts`
- `frontend/src/app/pages/project-overview/project-overview.component.html`
- `frontend/src/app/pages/project-settings/project-settings.component.ts`
- `frontend/src/app/pages/project-settings/project-settings.component.html`
- `frontend/src/app/pages/chatbots/chatbots.component.ts`
- `frontend/src/app/pages/chatbots/chatbots.component.html`
- `frontend/src/app/pages/chatbots/assistant-creation-wizard.component.ts`
- `frontend/src/app/pages/chatbots/assistant-creation-wizard.component.html`
- `frontend/src/app/pages/template-selection/template-selection.component.ts`
- `frontend/src/app/pages/template-selection/template-selection.component.html`
- `frontend/src/app/pages/assistant-overview/assistant-overview.component.ts`
- `frontend/src/app/pages/assistant-overview/assistant-overview.component.html`
- `frontend/src/app/pages/assistant-settings/assistant-settings.component.ts`
- `frontend/src/app/pages/assistant-settings/assistant-settings.component.html`
- `frontend/src/app/pages/flow-builder/flow-builder.component.ts` extrait ciblé setup seulement
- `backend/models/project.py`
- `backend/models/project_schema.py`
- `backend/models/chatbot.py`
- `backend/models/chatbot_schema.py`
- `backend/models/flow.py`
- `backend/models/version.py`
- `backend/models/user.py`
- `backend/routes/project_routes.py`
- `backend/routes/chatbot_routes.py`
- `backend/routes/flow_routes.py` extraits modèles seulement
- `backend/services/templates.py`
- `backend/services/auth.py`
- `backend/alembic/versions/99cb7c682e05_init.py`
- `backend/alembic/versions/d2a7a8c53301_add_chatbot_builder_flow.py`
- `backend/alembic/versions/c3d4e5f6a8b9_add_chatbot_template_provenance.py`
- `backend/alembic/versions/d7e8f9a0b1c2_add_project_lifecycle_fields.py`
- `backend/alembic/versions/e4f5a6b7c8d9_add_chatbot_ai_setup_provenance.py`
- `backend/alembic/versions/a8c2d4f6b901_add_chatbot_public_api_key.py`

