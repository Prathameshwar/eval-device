# Alex image prompt set

Created 2026-10-08 using the explicitly approved imagegen CLI/API fallback,
gpt-image-2, high quality. No key, credential or tenant data is included here.

## Hero portrait generation

Size: 1024x1536. Generated original: `output/imagegen/alex-portrait-v1.png`.
The deployed hero combines this portrait with an actual fictional-data UI capture.

```text
Use case: photorealistic-natural
Asset type: AI Evaluator public landing page patient portrait, subsequently composed with a real application screenshot.
Primary request: Create a premium editorial photograph of Alex, a fictional 35-year-old male schoolteacher, for a professional healthcare simulation product. Alex has a warm medium complexion, short neatly groomed dark brown hair, brown eyes, a subtly oval face, and a light natural beard. He wears a simple light blue button-down shirt with no logos. His expression is calm, approachable, and attentive. He is a simulated patient, not a clinician.
Scene/backdrop: A softly lit, clean clinical simulation room with warm white and very pale lavender surfaces. Blur background details. No other people.
Composition/framing: Waist-up portrait, seated upright, subject centered with generous breathing room above and beside his head. Face and shirt must remain clear for a narrower mobile crop. Natural proportions and posture. Hands rest naturally out of prominence. Portrait orientation.
Lighting/mood: Soft daylight, natural skin texture, restrained premium healthcare editorial photography, professional and welcoming.
Color palette: Warm white, pale lavender, deep navy accents, light blue shirt; avoid saturated hospital colors.
Constraints: Fictional character, no real person's likeness. No written text, labels, logos, watermarks, UI panels, screens, medical diagnoses, exposed anatomy, tubing, dramatic distress, or exaggerated smile. This portrait must serve as the identity reference for the second Alex image.
```

## Clinical scene edit

Size: 1536x1024. Input identity reference: the generated portrait above.
Generated original: `output/imagegen/alex-clinical-v1.png`.

```text
Use case: identity-preserve
Asset type: AI Evaluator Meet Alex section photograph.
Input image 1: Identity and wardrobe reference for the fictional patient Alex; preserve the same face, apparent age, hair, beard, skin tone, and light blue shirt.
Primary request: Show the exact same Alex from image 1 in a wider, polished clinical simulation setting. Preserve his identity and appearance. Alex is a fictional 35-year-old schoolteacher and simulated patient. He sits naturally in an uncluttered clinical interview chair beside a neatly made simulation bed, looking attentively toward the camera.
Scene/backdrop: Bright modern simulation room, soft warm white walls, discreet pale lavender details, a blurred bedside surface in the background. No other people or branded equipment.
Composition/framing: Landscape composition, waist-up or slightly wider, subject central, with safe space on all sides for a mobile crop. Natural sitting posture; normal hands if visible. Keep the scene quiet and uncluttered.
Lighting/mood: Match the soft natural daylight and restrained editorial photography of image 1. Approachable, professional, realistic skin texture.
Constraints: Preserve Alex's facial features, hairstyle, beard, age, skin tone, and shirt. Change only the camera framing and setting necessary for this scene. No text, watermark, logo, fabricated interface, needles, tubes, clinician clothing, distress, diagnosis, or additional people.
```

## Final project assets

- [Hero composition](../../platform/ui/apps/web/public/landing/alex-hero.webp)
- [Hero smaller variant](../../platform/ui/apps/web/public/landing/alex-hero-small.webp)
- [Clinical scene](../../platform/ui/apps/web/public/landing/alex-clinical.webp)
- [Clinical smaller variant](../../platform/ui/apps/web/public/landing/alex-clinical-small.webp)

Dimensions, file sizes and verification are recorded in
[release notes](../landing-page-release.md).
