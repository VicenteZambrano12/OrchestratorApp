import unittest
from unittest.mock import Mock, patch

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.pipeline.Pipeline import Pipeline
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.routinemaker.models import RoutineMakerResult, RoutineParameters


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Mock(spec=Orchestrator)
        self.routine_maker = Mock(spec=RoutineMaker)
        self.exercise_explainer = Mock(spec=ExerciseExplainer)
        self.past_routines_analyzer = Mock(spec=PastRoutinesAnalyzer)
        self.systems = {
            "routine_maker": self.routine_maker,
            "exercise_explainer": self.exercise_explainer,
            "past_routines_analyzer": self.past_routines_analyzer,
        }
        self.pipeline = Pipeline(self.orchestrator, **self.systems)

    def test_routes_and_invokes_only_selected_system_in_requested_language(self):
        query = "  My workout question  "
        for target, system in self.systems.items():
            for language in ("ES", "EN"):
                with self.subTest(target=target, language=language):
                    self.orchestrator.reset_mock()
                    for dependency in self.systems.values():
                        dependency.reset_mock()
                    self.orchestrator.route.return_value = target
                    result = self.pipeline.handle(query, language)
                    self.assertIs(result, system.handle.return_value)
                    self.orchestrator.route.assert_called_once_with(
                        {"query": query}, language=language
                    )
                    kwargs = {"language": language}
                    if target == "routine_maker":
                        kwargs.update(parameters=None, routine=None)
                    elif target == "past_routines_analyzer":
                        kwargs["history"] = None
                    system.handle.assert_called_once_with(query, **kwargs)
                    for other_target, dependency in self.systems.items():
                        if other_target != target:
                            dependency.handle.assert_not_called()

    def test_preserves_routine_state_and_result(self):
        self.orchestrator.route.return_value = "routine_maker"
        parameters = RoutineParameters(days_per_week=3)
        result = RoutineMakerResult(
            status="needs_parameters",
            parameters=parameters,
            message="What is your level?",
            routine=None,
        )
        self.routine_maker.handle.return_value = result
        self.assertIs(
            self.pipeline.handle(
                "Three days", "EN", parameters=parameters, routine="Previous routine"
            ),
            result,
        )
        self.routine_maker.handle.assert_called_once_with(
            "Three days", parameters=parameters, routine="Previous routine", language="EN"
        )

    def test_passes_history_to_analyzer(self):
        self.orchestrator.route.return_value = "past_routines_analyzer"
        self.pipeline.handle("Analyze my progress", "ES", history="Squat: 3x8 at 60kg")
        self.past_routines_analyzer.handle.assert_called_once_with(
            "Analyze my progress", history="Squat: 3x8 at 60kg", language="ES"
        )

    def test_no_system_returns_localized_message_without_creating_systems(self):
        for language in ("EN", "ES"):
            with self.subTest(language=language):
                selector = Mock(return_value="no_system")
                pipeline = Pipeline(Orchestrator(selector))
                with patch(
                    "systems.pipeline.Pipeline.RoutineMaker"
                ) as routine_maker, patch(
                    "systems.pipeline.Pipeline.ExerciseExplainer"
                ) as explainer, patch(
                    "systems.pipeline.Pipeline.PastRoutinesAnalyzer"
                ) as analyzer:
                    self.assertEqual(
                        pipeline.handle("What is the capital of Japan?", language),
                        Orchestrator.no_system_message(language),
                    )
                    routine_maker.assert_not_called()
                    explainer.assert_not_called()
                    analyzer.assert_not_called()
                self.assertEqual(selector.call_args.args[2], language)

    def test_defaults_to_english(self):
        self.orchestrator.route.return_value = "exercise_explainer"
        self.pipeline.handle("Explain squats")
        self.exercise_explainer.handle.assert_called_once_with(
            "Explain squats", language="EN"
        )

    def test_invalid_input_fails_before_dependency_creation(self):
        for query, language in (
            ("", "EN"), ("  ", "ES"), (None, "EN"), (123, "ES"),
            ("Explain squats", "en"), ("Explain squats", "FR"),
            ("Explain squats", None), ("Explain squats", ["EN"]),
        ):
            with self.subTest(query=query, language=language), patch(
                "systems.pipeline.Pipeline.Orchestrator.from_gemini"
            ) as factory:
                with self.assertRaises(ValueError):
                    Pipeline().handle(query, language)
                factory.assert_not_called()

    def test_default_dependencies_are_created_lazily_and_reused(self):
        orchestrator = Orchestrator(Mock(return_value="exercise_explainer"))
        with patch(
            "systems.pipeline.Pipeline.Orchestrator.from_gemini",
            return_value=orchestrator,
        ) as factory, patch(
            "systems.pipeline.Pipeline.ExerciseExplainer",
            return_value=self.exercise_explainer,
        ) as explainer:
            pipeline = Pipeline()
            factory.assert_not_called()
            explainer.assert_not_called()
            pipeline.handle("Explain squats", "ES")
            pipeline.handle("Explain bench press", "EN")
            factory.assert_called_once_with()
            explainer.assert_called_once_with()
            self.assertEqual(self.exercise_explainer.handle.call_count, 2)

    def test_unknown_target_raises_without_calling_any_system(self):
        self.orchestrator.route.return_value = "custom_system"
        with self.assertRaisesRegex(ValueError, "unsupported pipeline subsystem id"):
            self.pipeline.handle("My query", "EN")
        for system in self.systems.values():
            system.handle.assert_not_called()

    def test_routing_and_system_errors_propagate(self):
        error = RuntimeError("Provider unavailable")
        self.orchestrator.route.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.pipeline.handle("Explain squats", "EN")
        self.assertIs(caught.exception, error)
        for system in self.systems.values():
            system.handle.assert_not_called()
        self.orchestrator.route.side_effect = None
        self.orchestrator.route.return_value = "exercise_explainer"
        self.exercise_explainer.handle.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self.pipeline.handle("Explain squats", "EN")
        self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()
