from django.shortcuts import render

def index(request):
    return render(request, 'translation/index.html')


def translation_run(request, episode_id):
    return render(request, 'translation/translation_run.html', {'episode_id': episode_id})


def review_chatbot(request, translation_id):
    return render(request, 'translation/review_chatbot.html', {'translation_id': translation_id})


def translation_version_list(request, episode_id):
    return render(request, 'translation/translation_version_list.html', {'episode_id': episode_id})


def translation_version_delete(request, translation_id):
    return render(request, 'translation/translation_version_delete.html', {'translation_id': translation_id})
