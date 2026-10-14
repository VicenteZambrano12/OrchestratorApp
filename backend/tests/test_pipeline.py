import json
import unittest
from unittest.mock import Mock, patch

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.pipeline.Pipeline import Pipeline
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.func.handle_with_subsystem import handle_with_subsystem
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters


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

    def test_exercise_list_is_serialized_into_memory_and_reused(self):
        exercise = ExerciseExplanation(
            id=1, name="Barbell Bench Press", description=" Original ",
            instructions="Press.", icon_url=None, anatomy_diagram_url=None,
            media_urls=["first", "second"], llm_explanation="Explanation",
        )
        self.orchestrator.route.return_value = "exercise_explainer"
        self.exercise_explainer.handle.return_value = [exercise]
        setter, getter = Mock(), Mock()
        getter.get.return_value = {}
        pipeline = Pipeline(
            self.orchestrator, exercise_explainer=self.exercise_explainer,
            turn_setter=setter, turn_getter=getter,
        )
        result = pipeline.handle_with_subsystem("Explain bench", session_id="session")
        stored = setter.set.call_args.args[2]
        self.assertEqual(json.loads(stored), [exercise.model_dump()])
        self.assertEqual(result.response, [exercise])
        memory = {"user_query": "Explain bench", "system_response": stored}
        getter.get.return_value = {"1": memory}
        pipeline.handle_with_subsystem("Explain again", session_id="session")
        self.assertEqual(self.exercise_explainer.handle.call_args.kwargs["memory"], [memory])

    def test_execution_utility_returns_selected_subsystem_and_response(self):
        self.orchestrator.route.return_value = "exercise_explainer"
        result = handle_with_subsystem(self.pipeline, "Explain squats", "ES")
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.subsystem, "exercise_explainer")
        self.assertIs(result.response, self.exercise_explainer.handle.return_value)
        self.orchestrator.route.assert_called_once_with(
            {"query": "Explain squats"}, language="ES"
        )
        self.exercise_explainer.handle.assert_called_once_with(
            "Explain squats", language="ES"
        )

    def test_returns_selected_subsystem_and_unchanged_response_after_routing_once(self):
        for target, system in self.systems.items():
            for language in ("ES", "EN"):
                with self.subTest(target=target, language=language):
                    self.orchestrator.reset_mock()
                    for dependency in self.systems.values():
                        dependency.reset_mock()
                    self.orchestrator.route.return_value = target
                    result = self.pipeline.handle_with_subsystem(
                        "  My workout question  ", language, session_id="session", user_id=1,
                    )
                    self.assertIsInstance(result, PipelineResult)
                    self.assertEqual(result.subsystem, target)
                    self.assertIs(result.response, system.handle.return_value)
                    self.orchestrator.route.assert_called_once_with(
                        {"query": "  My workout question  "}, language=language
                    )
                    self.assertEqual(system.handle.call_count, 1)
                    for other_target, dependency in self.systems.items():
                        if other_target != target:
                            dependency.handle.assert_not_called()

    def test_metadata_no_match_does_not_invoke_any_system(self):
        self.orchestrator.route.return_value = "no_system"
        for language in ("ES", "EN"):
            with self.subTest(language=language):
                self.orchestrator.reset_mock()
                self.orchestrator.no_system_message.return_value = (
                    Orchestrator.no_system_message(language)
                )
                result = self.pipeline.handle_with_subsystem(
                    "What is the capital of Japan?", language
                )
                self.assertEqual(result.subsystem, "no_system")
                self.assertEqual(result.response, Orchestrator.no_system_message(language))
                self.assertEqual(self.orchestrator.route.call_count, 1)
                self.orchestrator.no_system_message.assert_called_once_with(language)
                for system in self.systems.values():
                    system.handle.assert_not_called()

    def test_metadata_preserves_structured_result_and_routine_state(self):
        self.orchestrator.route.return_value = "routine_maker"
        parameters = RoutineParameters(days_per_week=3)
        response = RoutineMakerResult(
            status="needs_parameters",
            parameters=parameters,
            message="What is your training level?",
            routine=None,
        )
        self.routine_maker.handle.return_value = response
        result = self.pipeline.handle_with_subsystem(
            "Three days", "EN", parameters=parameters, routine="Previous routine",
            session_id="session", user_id=1,
        )
        self.assertEqual(result.subsystem, "routine_maker")
        self.assertIs(result.response, response)
        self.routine_maker.handle.assert_called_once_with(
            "Three days", parameters=parameters, routine="Previous routine", language="EN",
            session_id="session", user_id=1,
        )

    def test_routes_and_invokes_only_selected_system_in_requested_language(self):
        query = "  My workout question  "
        for target, system in self.systems.items():
            for language in ("ES", "EN"):
                with self.subTest(target=target, language=language):
                    self.orchestrator.reset_mock()
                    for dependency in self.systems.values():
                        dependency.reset_mock()
                    self.orchestrator.route.return_value = target
                    result = self.pipeline.handle(query, language, session_id="session", user_id=1)
                    self.assertIs(result, system.handle.return_value)
                    self.orchestrator.route.assert_called_once_with(
                        {"query": query}, language=language
                    )
                    kwargs = {"language": language}
                    if target == "routine_maker":
                        kwargs.update(parameters=None, routine=None, session_id="session", user_id=1)
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
                "Three days", "EN", parameters=parameters, routine="Previous routine",
                session_id="session", user_id=1,
            ),
            result,
        )
        self.routine_maker.handle.assert_called_once_with(
            "Three days", parameters=parameters, routine="Previous routine", language="EN",
            session_id="session", user_id=1,
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
                    "utils.pipeline.func.handle_with_subsystem.RoutineMaker"
                ) as routine_maker, patch(
                    "utils.pipeline.func.handle_with_subsystem.ExerciseExplainer"
                ) as explainer, patch(
                    "utils.pipeline.func.handle_with_subsystem.PastRoutinesAnalyzer"
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

    def test_routine_requests_require_user_and_session_before_system_execution(self):
        self.orchestrator.route.return_value = "routine_maker"
        for kwargs in ({}, {"session_id": "session"}, {"user_id": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "require"):
                self.pipeline.handle("Make a routine", **kwargs)
        self.routine_maker.handle.assert_not_called()

    def test_invalid_input_fails_before_dependency_creation(self):
        for query, language in (
            ("", "EN"), ("  ", "ES"), (None, "EN"), (123, "ES"),
            ("Explain squats", "en"), ("Explain squats", "FR"),
            ("Explain squats", None), ("Explain squats", ["EN"]),
        ):
            with self.subTest(query=query, language=language), patch(
                "utils.pipeline.func.handle_with_subsystem.Orchestrator.from_gemini"
            ) as factory:
                with self.assertRaises(ValueError):
                    Pipeline().handle(query, language)
                factory.assert_not_called()

    def test_default_dependencies_are_created_lazily_and_reused(self):
        for target, class_name in (
            ("routine_maker", "RoutineMaker"),
            ("exercise_explainer", "ExerciseExplainer"),
            ("past_routines_analyzer", "PastRoutinesAnalyzer"),
        ):
            with self.subTest(target=target):
                system = self.systems[target]
                orchestrator = Orchestrator(Mock(return_value=target))
                with patch(
                    "utils.pipeline.func.handle_with_subsystem.Orchestrator.from_gemini",
                    return_value=orchestrator,
                ) as factory, patch(
                    f"utils.pipeline.func.handle_with_subsystem.{class_name}",
                    return_value=system,
                ) as system_factory:
                    pipeline = Pipeline()
                    factory.assert_not_called()
                    system_factory.assert_not_called()
                    pipeline.handle("My first workout question", "ES", session_id="session", user_id=1)
                    pipeline.handle("My second workout question", "EN", session_id="session", user_id=1)
                    factory.assert_called_once_with()
                    system_factory.assert_called_once_with()
                    self.assertEqual(system.handle.call_count, 2)

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
