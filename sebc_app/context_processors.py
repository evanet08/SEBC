"""
Context processors pour SEBC.
Injecte les modules autorisés dans le contexte de chaque template.
"""
from .models import Module, AccesModule, Membre


def sidebar_modules(request):
    """Injecte la liste des modules accessibles dans le contexte."""
    membre_id = request.session.get('membre_id')
    if not membre_id:
        return {'sidebar_modules': []}

    try:
        membre = Membre.objects.get(id=membre_id, est_actif=True)
    except Membre.DoesNotExist:
        return {'sidebar_modules': []}

    # Superadmin voit tout
    if membre.est_superadmin:
        modules = Module.objects.filter(est_actif=True, visible_sidebar=True).order_by('ordre')
        return {'sidebar_modules': modules}

    # Modules dont le rôle du membre a un AccesModule.peut_lire = True
    modules_autorises = Module.objects.filter(
        est_actif=True,
        visible_sidebar=True,
        acces__role=membre.role,
        acces__peut_lire=True,
        acces__est_actif=True,
    ).distinct().order_by('ordre')

    return {'sidebar_modules': modules_autorises}
