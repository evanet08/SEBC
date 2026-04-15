from django.db import models
import uuid
import hashlib
import random
import string
from django.utils import timezone


# ============================================================
# TYPES D'AYANTS DROITS
# ============================================================
class TypeAyantDroit(models.Model):
    """Types de liens de parenté acceptés par l'association SEBC Dushigikirane."""
    id = models.AutoField(primary_key=True)
    libelle = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    est_actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'type_ayant_droit'
        ordering = ['libelle']
        verbose_name = 'Type d\'ayant droit'
        verbose_name_plural = 'Types d\'ayants droits'

    def __str__(self):
        return self.libelle


# ============================================================
# PAYS
# ============================================================
class Pays(models.Model):
    """Pays de résidence des membres."""
    id = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=100, unique=True)
    code_iso = models.CharField(max_length=3, blank=True, null=True)
    indicatif_tel = models.CharField(max_length=10, blank=True, null=True)
    est_actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'pays'
        ordering = ['nom']
        verbose_name = 'Pays'
        verbose_name_plural = 'Pays'

    def __str__(self):
        return self.nom


# ============================================================
# CELLULE
# ============================================================
class Cellule(models.Model):
    """Cellule = unité organisationnelle de l'association (ex: A-000-067)."""
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True, help_text="Ex: A-000-067")
    nom = models.CharField(max_length=200, blank=True, null=True)
    pays = models.ForeignKey(Pays, on_delete=models.SET_NULL, null=True, blank=True)
    est_active = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cellule'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.nom or 'Sans nom'}"


# ============================================================
# STATUT MEMBRE
# ============================================================
STATUT_CHOICES = [
    ('EN_ATTENTE', 'En attente d\'approbation'),
    ('APPROUVE', 'Approuvé'),
    ('SUSPENDU', 'Suspendu'),
    ('RADIE', 'Radié'),
]

ROLE_CHOICES = [
    ('MEMBRE', 'Membre'),
    ('CHEF_CELLULE', 'Chef de Cellule'),
    ('CHARGE_APPROBATION', 'Chargé d\'Approbation'),
    ('CHARGE_FRAIS', 'Chargé des Frais'),
    ('COMPTABLE', 'Chargé de Comptabilité'),
    ('ADMIN', 'Administrateur'),
]


# ============================================================
# TYPES DE MEMBRES
# ============================================================
NIVEAU_TYPE_CHOICES = [
    ('NATIONAL', 'National'),
    ('CELLULE', 'Cellule'),
]


class TypeMembre(models.Model):
    """Type de membre — détermine le niveau d'accès et la portée."""
    id = models.AutoField(primary_key=True)
    libelle = models.CharField(max_length=100, unique=True,
                               help_text="Ex: Gestionnaire, Membre")
    niveau = models.CharField(max_length=20, choices=NIVEAU_TYPE_CHOICES,
                              blank=True, null=True,
                              help_text="Portée pour les gestionnaires : National ou Cellule")
    description = models.CharField(max_length=300, blank=True, null=True)
    peut_gerer_communication = models.BooleanField(default=False,
                                                    help_text="Peut envoyer des communications de masse")
    peut_approuver_membres = models.BooleanField(default=False)
    peut_gerer_finances = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'type_membre'
        ordering = ['libelle']
        verbose_name = 'Type de membre'
        verbose_name_plural = 'Types de membres'

    def __str__(self):
        niv = f" ({self.get_niveau_display()})" if self.niveau else ""
        return f"{self.libelle}{niv}"


# ============================================================
# MEMBRE — Table principale (PAS auth_user)
# ============================================================
class Membre(models.Model):
    """
    Table membre autonome : toutes les données d'identification sont ici.
    N'utilise PAS le système auth_user de Django.
    """
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Identification
    nom = models.CharField(max_length=150)
    prenom = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    telephone_whatsapp = models.CharField(max_length=30, help_text="Numéro WhatsApp (obligatoire)")
    telephone_canada = models.CharField(max_length=30, blank=True, null=True, help_text="Numéro canadien")

    # Localisation
    province_origine = models.CharField(max_length=150, blank=True, null=True, help_text="Province d'origine (Burundi)")
    ville_residence = models.CharField(max_length=150, blank=True, null=True, help_text="Ville de résidence")
    pays_residence = models.ForeignKey(Pays, on_delete=models.SET_NULL, null=True, blank=True, related_name='membres')
    adresse = models.TextField(blank=True, null=True)

    # Famille
    nom_pere = models.CharField(max_length=200, blank=True, null=True)
    nom_mere = models.CharField(max_length=200, blank=True, null=True)
    nom_conjoint = models.CharField(max_length=200, blank=True, null=True)
    noms_enfants = models.TextField(blank=True, null=True, help_text="Noms des enfants, séparés par des virgules")
    noms_freres_soeurs = models.TextField(blank=True, null=True, help_text="Noms des frères et sœurs")
    personnes_en_charge = models.IntegerField(default=0)

    # Parrainage / Référence
    personne_referante = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='membres_referes',
        help_text="Le membre qui a référé cette personne"
    )
    nom_personne_referante = models.CharField(max_length=200, blank=True, null=True)
    tel_personne_referante = models.CharField(max_length=30, blank=True, null=True)
    email_personne_referante = models.CharField(max_length=200, blank=True, null=True)

    # Association
    cellule = models.ForeignKey(Cellule, on_delete=models.SET_NULL, null=True, blank=True, related_name='membres')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_ATTENTE')
    role = models.CharField(max_length=25, choices=ROLE_CHOICES, default='MEMBRE')
    type_membre = models.ForeignKey(TypeMembre, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='membres', help_text="Type de membre")
    date_demande_adhesion = models.DateTimeField(auto_now_add=True)
    date_approbation = models.DateTimeField(null=True, blank=True)
    date_affectation_cellule = models.DateTimeField(null=True, blank=True)
    frais_adhesion_paye = models.BooleanField(default=False)
    date_paiement_frais = models.DateTimeField(null=True, blank=True)
    parrain_valide = models.BooleanField(default=False, help_text="Le parrain a validé ce membre")
    date_validation_parrain = models.DateTimeField(null=True, blank=True)

    # Sécurité / Authentification
    mot_de_passe_hash = models.CharField(max_length=128, blank=True, null=True)
    email_verifie = models.BooleanField(default=False)
    telephone_verifie = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expire = models.DateTimeField(null=True, blank=True)
    otp_type = models.CharField(max_length=20, blank=True, null=True)  # EMAIL, SMS
    derniere_connexion = models.DateTimeField(null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    est_superadmin = models.BooleanField(default=False)

    class Meta:
        db_table = 'membre'
        ordering = ['nom', 'prenom']
        verbose_name = 'Membre'
        verbose_name_plural = 'Membres'

    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.get_statut_display()})"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    def set_password(self, raw_password):
        """Hash le mot de passe avec SHA-256 + sel."""
        salt = uuid.uuid4().hex[:16]
        hashed = hashlib.sha256(f"{salt}{raw_password}".encode()).hexdigest()
        self.mot_de_passe_hash = f"{salt}${hashed}"

    def check_password(self, raw_password):
        """Vérifie un mot de passe contre le hash stocké."""
        if not self.mot_de_passe_hash:
            return False
        try:
            salt, hashed = self.mot_de_passe_hash.split('$', 1)
            return hashlib.sha256(f"{salt}{raw_password}".encode()).hexdigest() == hashed
        except (ValueError, AttributeError):
            return False

    def generate_otp(self, otp_type='EMAIL', expiry_minutes=15):
        """Génère un code OTP à 6 chiffres."""
        self.otp_code = ''.join(random.choices(string.digits, k=6))
        self.otp_expire = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
        self.otp_type = otp_type
        self.save(update_fields=['otp_code', 'otp_expire', 'otp_type'])
        return self.otp_code

    def verify_otp(self, code):
        """Vérifie le code OTP."""
        if not self.otp_code or not self.otp_expire:
            return False
        if timezone.now() > self.otp_expire:
            return False
        if self.otp_code != code:
            return False
        # Invalider le code après utilisation
        self.otp_code = None
        self.otp_expire = None
        self.save(update_fields=['otp_code', 'otp_expire'])
        return True

    def has_role(self, role):
        """Vérifie si le membre a un rôle donné."""
        return self.role == role or self.est_superadmin

    def is_gestionnaire(self):
        """Est-il un gestionnaire de l'association ?"""
        return self.role in ['CHEF_CELLULE', 'CHARGE_APPROBATION', 'CHARGE_FRAIS', 'COMPTABLE', 'ADMIN'] or self.est_superadmin


# ============================================================
# AYANTS DROITS (bénéficiaires en cas de décès)
# ============================================================
class AyantDroit(models.Model):
    """Ayant droit d'un membre = personne couverte en cas de décès."""
    id = models.AutoField(primary_key=True)
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='ayants_droits')
    type_lien = models.ForeignKey(TypeAyantDroit, on_delete=models.PROTECT, related_name='ayants_droits')
    nom = models.CharField(max_length=150)
    prenom = models.CharField(max_length=150)
    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=200, blank=True, null=True)
    est_actif = models.BooleanField(default=True)
    est_approuve = models.BooleanField(default=False, help_text="Approuvé par l'administration")
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ayant_droit'
        ordering = ['nom', 'prenom']
        verbose_name = 'Ayant droit'
        verbose_name_plural = 'Ayants droits'

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.type_lien.libelle})"



# ============================================================
# DOCUMENTS MEMBRE
# ============================================================
TYPE_DOCUMENT_CHOICES = [
    ('PHOTO_IDENTITE', 'Photo d\'identité'),
    ('PIECE_IDENTITE', 'Pièce d\'identité'),
    ('PREUVE_RESIDENCE', 'Preuve de résidence'),
    ('AUTRE', 'Autre document'),
]

class DocumentMembre(models.Model):
    """Documents téléchargés par un membre (pièce d'identité, photo, etc.)."""
    id = models.AutoField(primary_key=True)
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='documents')
    type_document = models.CharField(max_length=30, choices=TYPE_DOCUMENT_CHOICES)
    fichier = models.FileField(upload_to='documents/membres/%Y/%m/')
    nom_fichier = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=300, blank=True, null=True)
    date_upload = models.DateTimeField(auto_now_add=True)
    est_valide = models.BooleanField(default=False, help_text="Validé par un gestionnaire")

    class Meta:
        db_table = 'document_membre'
        ordering = ['-date_upload']
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'

    def __str__(self):
        return f"{self.get_type_document_display()} — {self.membre.nom_complet}"


# ============================================================
# NOTIFICATIONS GESTIONNAIRES
# ============================================================
class NotificationGestionnaire(models.Model):
    """Définit quels gestionnaires reçoivent les notifications d'adhésion."""
    id = models.AutoField(primary_key=True)
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='notifications_config')
    recevoir_demandes_adhesion = models.BooleanField(default=False)
    recevoir_cotisations = models.BooleanField(default=False)
    recevoir_demandes_soutien = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'notification_gestionnaire'

    def __str__(self):
        return f"Config notifications — {self.membre.nom_complet}"


# ============================================================
# PARAMÈTRES ASSOCIATION (table clé-valeur dynamique)
# ============================================================
TYPE_PARAMETRE_CHOICES = [
    ('INT', 'Entier'),
    ('FLOAT', 'Décimal'),
    ('STRING', 'Texte'),
    ('BOOL', 'Oui/Non'),
]

class ParametreAssociation(models.Model):
    """Paramètres dynamiques de l'association (clé-valeur)."""
    id = models.AutoField(primary_key=True)
    cle = models.CharField(max_length=100, unique=True, help_text="Ex: delai_approbation_jours")
    libelle = models.CharField(max_length=200, help_text="Nom lisible du paramètre")
    valeur = models.CharField(max_length=500, help_text="Valeur du paramètre")
    type_valeur = models.CharField(max_length=10, choices=TYPE_PARAMETRE_CHOICES, default='STRING')
    description = models.TextField(blank=True, null=True)
    categorie = models.CharField(max_length=100, default='general', help_text="Catégorie de regroupement")
    modifiable = models.BooleanField(default=True, help_text="Si False, seul un superadmin peut modifier")
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'parametre_association'
        ordering = ['categorie', 'libelle']
        verbose_name = 'Paramètre'
        verbose_name_plural = 'Paramètres'

    def __str__(self):
        return f"{self.libelle} = {self.valeur}"

    @staticmethod
    def get_valeur(cle, default=None):
        """Récupère la valeur d'un paramètre par sa clé."""
        try:
            p = ParametreAssociation.objects.get(cle=cle)
            if p.type_valeur == 'INT':
                return int(p.valeur)
            elif p.type_valeur == 'FLOAT':
                return float(p.valeur)
            elif p.type_valeur == 'BOOL':
                return p.valeur.lower() in ('true', '1', 'oui', 'yes')
            return p.valeur
        except ParametreAssociation.DoesNotExist:
            return default


# ============================================================
# PROVINCE (provinces d'origine)
# ============================================================
class Province(models.Model):
    """Provinces d'origine, rattachées à un pays."""
    id = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=150)
    pays = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name='provinces')
    est_actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'province'
        ordering = ['pays__nom', 'nom']
        unique_together = [['nom', 'pays']]
        verbose_name = 'Province'
        verbose_name_plural = 'Provinces'

    def __str__(self):
        return f"{self.nom} ({self.pays.nom})"


# ============================================================
# TYPE SOUTIEN (types de cas de soutien décès)
# ============================================================
class TypeSoutien(models.Model):
    """Types de soutien versé par l'association en cas de décès."""
    id = models.AutoField(primary_key=True)
    libelle = models.CharField(max_length=200, unique=True,
                               help_text="Ex: Décès du membre, Décès du conjoint")
    montant = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                  help_text="Montant du soutien en CAD")
    description = models.TextField(blank=True, null=True)
    nombre_temoins_requis = models.IntegerField(default=3,
                                                 help_text="Nombre de témoins requis pour la réclamation")
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'type_soutien'
        ordering = ['libelle']
        verbose_name = 'Type de soutien'
        verbose_name_plural = 'Types de soutien'

    def __str__(self):
        return f"{self.libelle} — {self.montant} CAD"


# ============================================================
# MODULES & ACCÈS (gestion dynamique du menu et permissions)
# ============================================================
class Module(models.Model):
    """Module de l'application — chaque entrée = un item dans la sidebar."""
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=50, unique=True, help_text="Identifiant technique (ex: membres, dashboard)")
    nom = models.CharField(max_length=100, help_text="Nom affiché dans la sidebar")
    description = models.CharField(max_length=300, blank=True, null=True)
    icone = models.CharField(max_length=80, default='fas fa-cube', help_text="Classe FontAwesome (ex: fas fa-users)")
    couleur = models.CharField(max_length=30, default='#60a5fa', help_text="Couleur de l'icône (hex)")
    url = models.CharField(max_length=200, help_text="URL relative du module (ex: /membres/)")
    ordre = models.IntegerField(default=0, help_text="Ordre d'affichage dans la sidebar")
    est_actif = models.BooleanField(default=True)
    visible_sidebar = models.BooleanField(default=True, help_text="Affiché dans la sidebar")
    requiert_approbation = models.BooleanField(default=False, help_text="Accessible seulement aux membres approuvés")
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'module'
        ordering = ['ordre', 'nom']
        verbose_name = 'Module'
        verbose_name_plural = 'Modules'

    def __str__(self):
        return f"{self.nom} ({self.code})"


class AccesModule(models.Model):
    """Droits d'accès par rôle à un module donné."""
    id = models.AutoField(primary_key=True)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='acces')
    role = models.CharField(max_length=25, choices=ROLE_CHOICES, help_text="Rôle ayant accès à ce module")
    peut_lire = models.BooleanField(default=True)
    peut_ecrire = models.BooleanField(default=False)
    peut_supprimer = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'acces_module'
        unique_together = ('module', 'role')
        ordering = ['module__ordre', 'role']
        verbose_name = 'Accès module'
        verbose_name_plural = 'Accès modules'

    def __str__(self):
        return f"{self.get_role_display()} → {self.module.nom}"


# ============================================================
# COMMUNICATION (messagerie interne style WhatsApp)
# ============================================================
SCOPE_COMM_CHOICES = [
    ('individual', 'Membre individuel'),
    ('cellule', 'Cellule entière'),
    ('national', 'Tous les membres'),
    ('type_membre', 'Par type de membre'),
    ('custom_group', 'Groupe personnalisé'),
]

DIRECTION_COMM_CHOICES = [
    ('out', 'Sortant'),
    ('in', 'Entrant'),
]

STATUS_COMM_CHOICES = [
    ('sent', 'Envoyé'),
    ('delivered', 'Délivré'),
    ('read', 'Lu'),
    ('failed', 'Échoué'),
]


class Communication(models.Model):
    """Message de communication interne entre membres SEBC."""
    id = models.AutoField(primary_key=True)

    # Expéditeur
    sender = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='messages_envoyes')
    sender_name = models.CharField(max_length=255, blank=True, default='')

    # Portée et direction
    scope = models.CharField(max_length=20, choices=SCOPE_COMM_CHOICES, default='individual')
    direction = models.CharField(max_length=5, choices=DIRECTION_COMM_CHOICES, default='out')

    # Cibles (selon le scope)
    target_membre = models.ForeignKey(Membre, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='messages_recus',
                                       help_text="Pour scope=individual")
    target_cellule = models.ForeignKey(Cellule, on_delete=models.SET_NULL, null=True, blank=True,
                                        help_text="Pour scope=cellule")
    target_type_membre = models.ForeignKey(TypeMembre, on_delete=models.SET_NULL, null=True, blank=True,
                                            help_text="Pour scope=type_membre")
    target_group = models.ForeignKey('CommunicationGroupe', on_delete=models.SET_NULL, null=True, blank=True,
                                      help_text="Pour scope=custom_group")

    # Contenu
    subject = models.CharField(max_length=255, blank=True, default='')
    message = models.TextField()

    # Pièce jointe
    attachment = models.FileField(upload_to='communication/attachments/%Y/%m/', blank=True, null=True)
    attachment_name = models.CharField(max_length=255, blank=True, null=True)
    attachment_type = models.CharField(max_length=50, blank=True, null=True)

    # Fil de discussion
    thread_id = models.CharField(max_length=120, blank=True, default='', db_index=True)

    # Statut
    status = models.CharField(max_length=20, choices=STATUS_COMM_CHOICES, default='sent')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'communication'
        ordering = ['created_at']
        verbose_name = 'Communication'
        verbose_name_plural = 'Communications'
        indexes = [
            models.Index(fields=['thread_id', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.direction}] {self.sender_name} → {self.get_scope_display()} | {self.message[:50]}"


class CommunicationGroupe(models.Model):
    """Groupe de discussion personnalisé."""
    id = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True, default='')
    createur = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='groupes_crees')
    couleur_avatar = models.CharField(max_length=20, default='#128c7e')
    est_actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'communication_groupe'
        ordering = ['-created_at']
        verbose_name = 'Groupe de communication'
        verbose_name_plural = 'Groupes de communication'

    def __str__(self):
        return self.nom


class CommunicationGroupeMembre(models.Model):
    """Membre d'un groupe de communication."""
    id = models.AutoField(primary_key=True)
    groupe = models.ForeignKey(CommunicationGroupe, on_delete=models.CASCADE, related_name='membres_groupe')
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='groupes_comm')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'communication_groupe_membre'
        unique_together = ('groupe', 'membre')
        verbose_name = 'Membre de groupe'
        verbose_name_plural = 'Membres de groupes'

    def __str__(self):
        return f"{self.membre.nom_complet} → {self.groupe.nom}"


# ============================================================
# RÉUNIONS / VIDÉOCONFÉRENCES
# ============================================================
MEETING_STATUS_CHOICES = [
    ('scheduled', 'Planifiée'),
    ('live', 'En cours'),
    ('ended', 'Terminée'),
    ('cancelled', 'Annulée'),
]


class Meeting(models.Model):
    """Réunion vidéo planifiée avec Jitsi Meet."""
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True, default='')
    room_name = models.CharField(max_length=100, unique=True, db_index=True)
    join_token = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='meetings_crees')
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=60)
    status = models.CharField(max_length=20, choices=MEETING_STATUS_CHOICES, default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meeting'
        ordering = ['-scheduled_at']
        verbose_name = 'Réunion'
        verbose_name_plural = 'Réunions'

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def share_url(self):
        return f"https://sebc-dushigikirane.pro/communication/?join={self.join_token}"

    @property
    def jitsi_url(self):
        return f"https://meet.jit.si/{self.room_name}"


class MeetingInvite(models.Model):
    """Invitation à une réunion."""
    id = models.AutoField(primary_key=True)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='invites')
    membre = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='meeting_invites')
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meeting_invite'
        unique_together = ('meeting', 'membre')
        verbose_name = 'Invitation réunion'
        verbose_name_plural = 'Invitations réunions'

    def __str__(self):
        return f"{self.membre.nom_complet} → {self.meeting.title}"
