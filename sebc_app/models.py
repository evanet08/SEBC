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
    date_demande_adhesion = models.DateTimeField(auto_now_add=True)
    date_approbation = models.DateTimeField(null=True, blank=True)
    date_affectation_cellule = models.DateTimeField(null=True, blank=True)
    frais_adhesion_paye = models.BooleanField(default=False)
    date_paiement_frais = models.DateTimeField(null=True, blank=True)

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
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ayant_droit'
        ordering = ['nom', 'prenom']
        verbose_name = 'Ayant droit'
        verbose_name_plural = 'Ayants droits'

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.type_lien.libelle})"


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
