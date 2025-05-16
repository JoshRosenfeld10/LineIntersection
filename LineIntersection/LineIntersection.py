import numpy as np
import slicer
import qt
import ctk
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)
from slicer.parameterNodeWrapper import parameterNodeWrapper
from slicer import vtkMRMLMarkupsFiducialNode


class LineIntersection(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        parent.title = "Line Intersection"
        parent.categories = ["Examples"]
        parent.contributors = ["Josh Rosenfeld (Perk Lab)"]
        parent.helpText = (
            "Compute the closest point between two lines defined by two points "
            "and direction vectors."
        )


@parameterNodeWrapper
class LineIntersectionParameterNode:
    points: vtkMRMLMarkupsFiducialNode
    d1: list[float] = [1.0, 0.0, 0.0]
    d2: list[float] = [0.0, 1.0, 0.0]
    autoUpdate: bool = False


class LineIntersectionWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pointNodeObserver = None
        self._creating = False

    def setup(self):
        super().setup()
        # Logic and parameter node
        self.logic = LineIntersectionLogic()
        self.parameterNode = self.logic.getParameterNode()

        # Find or create fiducial node
        fn = slicer.mrmlScene.GetFirstNodeByName("LineIntersectionPoints")

        # If fiducial node isn't found, create a new one
        if not fn:
            fn = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode", "LineIntersectionPoints"
            )
            for _ in range(3):
                fn.AddControlPoint(0.0, 0.0, 0.0)

        # lock P3 so it’s read-only in the scene
        fn.SetNthControlPointLocked(2, True)
        self.parameterNode.points = fn
        self.pointNode = fn

        # Build UI
        self._creating = True
        inputs = ctk.ctkCollapsibleButton()
        inputs.text = "Inputs"
        self.layout.addWidget(inputs)
        form = qt.QFormLayout(inputs)

        # Slider factory
        def makeSlider(default, type="P"):
            type = type.upper()
            s = ctk.ctkSliderWidget()
            s.minimum = -1.0 if type == "D" else -100.0
            s.maximum = 1.0 if type == "D" else 100.0
            s.singleStep = 0.01 if type == "D" else 0.1
            s.decimals = 2
            s.value = default
            return s

        # P1 sliders
        self.p1Sliders = [makeSlider(0.0, "P") for _ in range(3)]
        form.addRow("P1 X", self.p1Sliders[0])
        form.addRow("P1 Y", self.p1Sliders[1])
        form.addRow("P1 Z", self.p1Sliders[2])

        # P2 sliders
        self.p2Sliders = [makeSlider(0.0, "P") for _ in range(3)]
        form.addRow("P2 X", self.p2Sliders[0])
        form.addRow("P2 Y", self.p2Sliders[1])
        form.addRow("P2 Z", self.p2Sliders[2])

        # d1 sliders
        self.d1Sliders = [makeSlider(v, "D") for v in self.parameterNode.d1]
        form.addRow("d1 X", self.d1Sliders[0])
        form.addRow("d1 Y", self.d1Sliders[1])
        form.addRow("d1 Z", self.d1Sliders[2])

        # d2 sliders
        self.d2Sliders = [makeSlider(v, "D") for v in self.parameterNode.d2]
        form.addRow("d2 X", self.d2Sliders[0])
        form.addRow("d2 Y", self.d2Sliders[1])
        form.addRow("d2 Z", self.d2Sliders[2])

        # Outputs
        outputs = ctk.ctkCollapsibleButton()
        outputs.text = "Outputs"
        self.layout.addWidget(outputs)
        outForm = qt.QFormLayout(outputs)
        self.intersectionLabel = qt.QLabel()
        outForm.addRow("(Closest) Intersection Point:", self.intersectionLabel)

        # Observers
        self.pointNodeObserver = self.pointNode.AddObserver(
            slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
            self.onMarkupModified
        )

        # Slider connections
        allSliders = (
            self.p1Sliders
            + self.p2Sliders
            + self.d1Sliders
            + self.d2Sliders
        )
        for sl in allSliders:
            sl.connect("valueChanged(double)", self.onSliderModified)

        # Initial synchronization
        self.updateFromSliders()
        self._creating = False

    def cleanup(self):
        """
        Called when the module widget is destroyed or reloaded. Safely remove observers.
        """
        if self.pointNodeObserver is not None:
            self.pointNode.RemoveObserver(self.pointNodeObserver)
            self.pointNodeObserver = None

        super().cleanup()

    def onSliderModified(self, value):
        """
        Called from GUI connection whenever sliders are modified.
        """
        if self._creating:
            return
        self.updateFromSliders()

    def onMarkupModified(self, caller, event):
        """
        Called from observer whenever markup points are modified.
        """
        if self._creating:
            return
        self.updateFromMarkups()

    def updateFromSliders(self):
        """
        Update markups from slider values and compute P3.
        """
        self._creating = True

        # Update P1, P2
        p1 = [s.value for s in self.p1Sliders]
        p2 = [s.value for s in self.p2Sliders]
        self.pointNode.SetNthControlPointPosition(0, *p1)
        self.pointNode.SetNthControlPointPosition(1, *p2)

        # Update directions in parameter node
        self.parameterNode.d1 = [s.value for s in self.d1Sliders]
        self.parameterNode.d2 = [s.value for s in self.d2Sliders]

        # Compute and set P3
        self.updateP3Position(p1, p2)
        self._creating = False

    def updateFromMarkups(self):
        """
        Update sliders from markup point positions and compute P3.
        """
        self._creating = True

        # Read P1, P2 positions
        p1 = list(self.pointNode.GetNthControlPointPositionVector(0))
        p2 = list(self.pointNode.GetNthControlPointPositionVector(1))

        # Set slider values from P1 and P2 positions
        for sl, v in zip(self.p1Sliders, p1):
            sl.value = v
        for sl, v in zip(self.p2Sliders, p2):
            sl.value = v

        # Compute and set P3
        self.updateP3Position(p1, p2)
        self._creating = False

    def updateP3Position(self, p1, p2):
        """
        Computes P3 position as closest point of intersection between lines 
        defined by (P1, d1) and (P2, d2) and updates position in scene.
        """
        p3 = self.logic.computeClosestPointOfIntersection(
            p1, self.parameterNode.d1, p2, self.parameterNode.d2
        )
        wasModifying = self.pointNode.StartModify()
        self.pointNode.SetNthControlPointPosition(2, *p3)
        self.pointNode.EndModify(wasModifying)
        self.intersectionLabel.text = f"{tuple(round(x,2) for x in p3)}"


class LineIntersectionLogic(ScriptedLoadableModuleLogic):
    def getParameterNode(self):
        return LineIntersectionParameterNode(super().getParameterNode())

    def computeClosestPointOfIntersection(self, p1, d1, p2, d2):
        """
        Computes and returns closest point of intersection between lines defined by
        (P1, d1) and (P2, d2).
        """
        # If either direction vector is zero, default intersection to origin
        # to avoid dividing by zero
        if np.linalg.norm(d1) == 0 or np.linalg.norm(d2) == 0:
            return [0.0, 0.0, 0.0]

        # Convert to numpy arrays
        p1, p2, d1, d2 = map(np.array, (p1, p2, d1, d2), [float] * 4)

        # Compute closest point of intersection
        cross = np.cross(d1, d2)
        denom = np.linalg.norm(cross) ** 2
        if denom == 0:
            t = np.dot(p2 - p1, d1) / np.dot(d1, d1)
            closest = (p1 + t * d1 + p2) / 2.0
        else:
            t1 = np.linalg.det([p2 - p1, d2, cross]) / denom
            t2 = np.linalg.det([p2 - p1, d1, cross]) / denom
            c1 = p1 + t1 * d1
            c2 = p2 + t2 * d2
            closest = (c1 + c2) / 2.0

        return closest.tolist()
