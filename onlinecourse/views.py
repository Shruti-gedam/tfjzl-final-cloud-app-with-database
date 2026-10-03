from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from django.contrib.auth import login, logout, authenticate
from django.urls import reverse
from django.views import generic
import logging

# Import the models used by these views
from .models import Course, Enrollment, Choice, Submission

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        try:
            User.objects.get(username=username)
            context['message'] = "User already exists."
            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect('onlinecourse:index')


def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."

    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if user.is_authenticated:
        return Enrollment.objects.filter(user=user, course=course).exists()
    return False


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_details_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if user.is_authenticated and not check_if_enrolled(user, course):
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse('onlinecourse:course_details', args=(course.id,))
    )


def extract_answers(request):
    """Return the selected choice IDs from the exam form."""
    answers = []

    # Supports the form field name used in course_details_bootstrap.html
    for value in request.POST.getlist('choices'):
        try:
            answers.append(int(value))
        except (TypeError, ValueError):
            pass

    # Also supports fields named choice_1, choice_2, etc.
    for key in request.POST:
        if key.startswith('choice'):
            for value in request.POST.getlist(key):
                try:
                    answers.append(int(value))
                except (TypeError, ValueError):
                    pass

    return list(set(answers))


def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    if request.method != 'POST':
        return HttpResponseRedirect(
            reverse('onlinecourse:course_details', args=(course_id,))
        )

    course = get_object_or_404(Course, pk=course_id)
    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(enrollment=enrollment)
    selected_ids = extract_answers(request)

    selected_choices = Choice.objects.filter(
        id__in=selected_ids,
        question__course=course
    )
    submission.choices.set(selected_choices)

    return HttpResponseRedirect(
        reverse(
            'onlinecourse:exam_result',
            args=(course.id, submission.id)
        )
    )


def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course
    )

    selected_ids = set(
        submission.choices.values_list('id', flat=True)
    )
    question_list = []
    score = 0
    total_score = 0

    for question in course.question_set.all():
        choices = list(question.choice_set.all())
        correct_ids = {
            choice.id for choice in choices if choice.is_correct
        }
        question_choice_ids = {choice.id for choice in choices}
        selected_for_question = selected_ids & question_choice_ids

        is_correct = (
            bool(correct_ids)
            and selected_for_question == correct_ids
        )

        question_score = question.grade if is_correct else 0
        score += question_score
        total_score += question.grade

        # These values are available to the result template.
        question.is_correct = is_correct
        question.score = question_score

        for choice in choices:
            choice.is_selected = choice.id in selected_ids

        question.result_choices = choices
        question_list.append(question)

    context = {
        'course': course,
        'submission': submission,
        'question_list': question_list,
        'score': score,
        'grade': score,
        'total_score': total_score,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )