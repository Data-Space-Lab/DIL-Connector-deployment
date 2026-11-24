{{/*
Compute API/worker split (Data-Space-Lab/DIL-Connector-source#73).
Everything here renders only when dataplane.compute.enabled is true.
*/}}

{{- define "dil-connector.compute.image" -}}
{{- $c := .Values.dataplane.compute -}}
{{- $repository := default .Values.dataplane.image.repository $c.image.repository -}}
{{- $digest := required "dataplane.compute.image.digest (sha256:...) is required when dataplane.compute.enabled is true" $c.image.digest -}}
{{- if not (hasPrefix "sha256:" $digest) -}}
{{- fail "dataplane.compute.image.digest must be an immutable sha256:... digest" -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end -}}

{{/*
Everything API and worker must share. Any change rolls both Deployments
together (checksum annotation). Worker replicas and resources are excluded.
*/}}
{{- define "dil-connector.compute.checksum" -}}
{{- $c := .Values.dataplane.compute -}}
{{- $shared := dict
  "image" (include "dil-connector.compute.image" .)
  "sourceRevision" $c.sourceRevision
  "imageRevision" $c.imageRevision
  "configVersion" $c.configVersion
  "protectedSecret" $c.protectedSecret
  "settingsConfigMap" $c.settingsConfigMap
  "runtimeEnvSecret" $c.runtimeEnvSecret
  "helperSsh" $c.worker.helperSsh
  "env" $c.env
  "hostAliases" $c.hostAliases
  "settingsPath" .Values.dataplane.configStorage.path
-}}
{{- toJson $shared | sha256sum -}}
{{- end -}}

{{- define "dil-connector.compute.labels" -}}
app.kubernetes.io/name: dil-connector
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: dil-connector
{{- end -}}

{{- define "dil-connector.compute.podAnnotations" -}}
checksum/compute-config: {{ include "dil-connector.compute.checksum" . }}
dil-connector/compute-config-version: {{ .Values.dataplane.compute.configVersion | quote }}
{{- end -}}

{{/* Environment shared verbatim by API, worker and migration Job. */}}
{{- define "dil-connector.compute.env" -}}
{{- $c := .Values.dataplane.compute -}}
{{- $publicBaseUrl := trimSuffix "/" .Values.connector.publicBaseUrl -}}
- name: DIL_CONNECTOR_SOURCE_REVISION
  value: {{ required "dataplane.compute.sourceRevision is required when dataplane.compute.enabled is true" $c.sourceRevision | quote }}
- name: DIL_CONNECTOR_IMAGE_REVISION
  value: {{ required "dataplane.compute.imageRevision is required when dataplane.compute.enabled is true" $c.imageRevision | quote }}
- name: DATAPLANE_COMPUTE_ENABLED
  value: "true"
- name: DATAPLANE_COMPUTE_PUBLIC_ENDPOINT
  value: {{ default (printf "%s/compute/v1alpha1" $publicBaseUrl) $c.publicEndpoint | quote }}
- name: DATAPLANE_COMPUTE_MANAGEMENT_ORIGIN
  value: {{ default $publicBaseUrl $c.managementOrigin | quote }}
{{- range $name := keys $c.env | sortAlpha }}
- name: {{ $name }}
  value: {{ index $c.env $name | quote }}
{{- end }}
{{- end -}}

{{/*
Kubernetes Secret/ConfigMap volumes expose every key as a symlink into
..data, and the source rejects symlinked or group/world-readable protected
files. An init container from the same image copies the projected files into
an in-memory emptyDir as regular 0400 files; the main container mounts that
directory read-only at /run/secrets, the path the Compose reference uses.
Argument: dict "root" $ "helper" bool.
*/}}
{{- define "dil-connector.compute.initContainer" -}}
{{- $root := .root -}}
- name: protected-files
  image: {{ include "dil-connector.compute.image" $root | quote }}
  imagePullPolicy: {{ $root.Values.dataplane.compute.image.pullPolicy | quote }}
  command:
    - /bin/sh
    - -ec
    - |
      umask 077
      for source in /protected-source/*; do
        [ -f "$source" ] || continue
        cp -L "$source" "/run/secrets/${source##*/}"
        chmod 0400 "/run/secrets/${source##*/}"
      done
  volumeMounts:
    - name: compute-protected-source
      mountPath: /protected-source
      readOnly: true
    - name: compute-protected
      mountPath: /run/secrets
  resources:
    requests:
      cpu: 10m
      memory: 16Mi
    limits:
      cpu: 100m
      memory: 64Mi
{{- end -}}

{{- define "dil-connector.compute.volumes" -}}
{{- $root := .root -}}
{{- $c := $root.Values.dataplane.compute -}}
- name: compute-protected
  emptyDir:
    medium: Memory
    sizeLimit: {{ $c.protectedSizeLimit | quote }}
- name: compute-protected-source
  projected:
    defaultMode: 0400
    sources:
      - secret:
          name: {{ required "dataplane.compute.protectedSecret is required when dataplane.compute.enabled is true" $c.protectedSecret | quote }}
{{- if $c.settingsConfigMap }}
      - configMap:
          name: {{ $c.settingsConfigMap | quote }}
{{- end }}
{{- if .helper }}
      - secret:
          name: {{ required "dataplane.compute.worker.helperSsh.secretName is required when dataplane.compute.enabled is true" $c.worker.helperSsh.secretName | quote }}
          items:
            - key: {{ $c.worker.helperSsh.keyKey | quote }}
              path: {{ $c.worker.helperSsh.keyKey | quote }}
            - key: {{ $c.worker.helperSsh.knownHostsKey | quote }}
              path: {{ $c.worker.helperSsh.knownHostsKey | quote }}
{{- end }}
{{- end -}}
