"""Management UI for page builder (Super/Co Super Admin only)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from accounts.models import User
from common.mixins import ManagementSystemGateMixin
from common.models import ManagementSystem
from .forms import (
    AnimationPresetForm,
    PageBlockForm,
    PageTemplateForm,
    ThemeForm,
)
from .models import AnimationPreset, PageBlock, PageTemplate, Theme


class PageBuilderAccessMixin(
    ManagementSystemGateMixin, LoginRequiredMixin, UserPassesTestMixin
):
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def test_func(self):
        role = self.request.user.role
        return role in {User.Role.SUPER_ADMIN, User.Role.CO_SUPER_ADMIN}

    def handle_no_permission(self):
        messages.error(self.request, "Super/Co Super Admin access required.")
        return redirect("common:welcome")


class PageTemplateListView(PageBuilderAccessMixin, TemplateView):
    template_name = "pagebuilder/page_template_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["templates"] = PageTemplate.objects.all().order_by("slug")
        context["themes"] = Theme.objects.all().order_by("name")
        context["animations"] = AnimationPreset.objects.all().order_by("name")
        return context


class ThemeCreateView(PageBuilderAccessMixin, FormView):
    template_name = "pagebuilder/theme_form.html"
    form_class = ThemeForm
    success_url = reverse_lazy("pagebuilder:templates")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Theme saved.")
        return super().form_valid(form)


class AnimationCreateView(PageBuilderAccessMixin, FormView):
    template_name = "pagebuilder/animation_form.html"
    form_class = AnimationPresetForm
    success_url = reverse_lazy("pagebuilder:templates")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Animation preset saved.")
        return super().form_valid(form)


class PageTemplateEditView(PageBuilderAccessMixin, FormView):
    template_name = "pagebuilder/page_template_edit.html"
    form_class = PageTemplateForm
    success_url = reverse_lazy("pagebuilder:templates")

    def dispatch(self, request, *args, **kwargs):
        self.template_obj = get_object_or_404(PageTemplate, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.template_obj
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        BlockFormSet = modelformset_factory(
            PageBlock,
            form=PageBlockForm,
            extra=0,
        )
        context["template_obj"] = self.template_obj
        context["block_formset"] = kwargs.get("block_formset") or BlockFormSet(
            queryset=self.template_obj.blocks.all()
        )
        return context

    def post(self, request, *args, **kwargs):
        BlockFormSet = modelformset_factory(
            PageBlock,
            form=PageBlockForm,
            extra=0,
        )
        form = self.get_form()
        formset = BlockFormSet(
            request.POST,
            queryset=self.template_obj.blocks.all(),
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            blocks = formset.save(commit=False)
            for block in blocks:
                block.template = self.template_obj
                block.save()
            messages.success(self.request, "Page template and blocks updated.")
            return redirect("pagebuilder:edit_template", pk=self.template_obj.pk)
        return self.render_to_response(self.get_context_data(form=form, block_formset=formset))
